"""Business-logic layer for PayPal payments.

This module owns everything that happens *after* we have a response from
PayPal's API - creating/looking up `Payment` rows, deciding when a
Payment is "final", activating a plan on a user's `Profile`, and turning
a webhook body into a database update. It deliberately contains NO direct
HTTP calls to PayPal - all of that lives in `billing/paypal.py`. Views
should call into this module rather than touching `Payment`/`Profile`
directly, so the HTTP-handling code in `views.py` stays thin.

Concurrency note: the return_url view and the webhook can both race to
settle the same Payment (e.g. the buyer approves, the webhook fires
almost immediately, and the browser redirect lands a moment later).
Every function below that mutates a Payment wraps its critical section in
`transaction.atomic()` + `select_for_update()` so only one of the two
ever wins the race; the loser sees the row already `is_final` and is a
no-op.
"""
import logging
from typing import Optional

from django.db import transaction
from django.utils import timezone

from . import paypal
from .models import Payment
from .plans import PLAN_NAMES, PLAN_PRICES_USD

logger = logging.getLogger(__name__)


class DuplicateCheckoutError(Exception):
    """Raised when a user tries to start a second checkout for a plan
    while a previous attempt for that same plan is still pending."""


def start_checkout(*, user, plan: str, email: str, return_url: str, cancel_url: str) -> Payment:
    """Create a pending Payment row and a matching PayPal order.

    Returns the Payment with `paypal_order_id`/`checkout_url` populated.
    Raises `paypal.PayPalError` if PayPal could not be reached, and
    `DuplicateCheckoutError` if the user already has an unresolved
    checkout in flight for this exact plan (guards against a
    double-click/double-submit creating two live orders).
    """
    if plan not in PLAN_PRICES_USD:
        raise ValueError(f'Unknown plan: {plan!r}')

    if Payment.objects.filter(user=user, plan=plan, status='pending').exists():
        raise DuplicateCheckoutError(
            'A payment for this plan is already in progress. Please finish or cancel it first.'
        )

    amount = PLAN_PRICES_USD[plan]
    tx_ref = paypal.generate_tx_ref(prefix=f'mw-{user.id}')

    with transaction.atomic():
        payment = Payment.objects.create(
            user=user,
            plan=plan,
            tx_ref=tx_ref,
            amount=amount,
            currency='USD',
            status='pending',
            email=email,
        )

    # Deliberately outside the atomic block: this is a network call, and
    # we don't want to hold a DB transaction open for the duration of an
    # HTTP round-trip to PayPal.
    try:
        data = paypal.create_order(
            amount=amount,
            currency='USD',
            tx_ref=tx_ref,
            return_url=return_url,
            cancel_url=cancel_url,
            description=f'MoneyWise {PLAN_NAMES.get(plan, plan)} plan subscription',
        )
    except paypal.PayPalError as exc:
        payment.status = 'failed'
        payment.failure_reason = str(exc)
        payment.save(update_fields=['status', 'failure_reason', 'updated_at'])
        logger.warning('Checkout create order failed for user_id=%s tx_ref=%s: %s', user.id, tx_ref, exc)
        raise

    approve_url = next((l.get('href') for l in data.get('links', []) if l.get('rel') == 'approve'), '')
    payment.paypal_order_id = data.get('id', '')
    payment.checkout_url = approve_url
    payment.raw_create_response = data
    payment.save(update_fields=['paypal_order_id', 'checkout_url', 'raw_create_response', 'updated_at'])

    logger.info('Checkout started user_id=%s plan=%s tx_ref=%s order_id=%s', user.id, plan, tx_ref, payment.paypal_order_id)
    return payment


def _activate_subscription(payment: Payment) -> None:
    """Grant the plan to the user once a payment is confirmed successful.

    Safe to call more than once (idempotent) - re-applying the same plan
    to the same profile is a no-op in effect. Must be called from inside
    a `transaction.atomic()` block that already holds a row lock on
    `payment`, so a concurrent webhook/return_url race can't activate the
    same purchase twice or apply it out of order.
    """
    profile = payment.user.profile
    profile.plan = payment.plan
    profile.subscription_status = 'active'
    profile.current_period_end = timezone.now() + timezone.timedelta(days=30)
    profile.save(update_fields=['plan', 'subscription_status', 'current_period_end'])
    logger.info(
        'Activated plan=%s for user_id=%s via tx_ref=%s',
        payment.plan, payment.user_id, payment.tx_ref,
    )


def downgrade_to_free(profile) -> None:
    """Reset a profile back to the Free plan (used by the billing portal's
    'cancel subscription' action)."""
    profile.plan = 'free'
    profile.subscription_status = ''
    profile.current_period_end = None
    profile.save(update_fields=['plan', 'subscription_status', 'current_period_end'])
    logger.info('Downgraded user_id=%s to free plan', profile.user_id)


def capture_and_sync(payment_id: int) -> Payment:
    """Capture the PayPal order for a Payment (this is the call that
    actually moves the money) and update the local row to match.

    Takes a primary key rather than an instance so we can grab a
    row-level lock (`select_for_update`) on the *current* database state
    right before deciding what to do - this is the only place allowed to
    mark a Payment 'success' from a fresh capture. Never trust a redirect
    query string or a webhook body on its own; always confirm with
    PayPal's API first, per PayPal's guidance:
    https://developer.paypal.com/docs/api/webhooks/v1/#verify-webhook-signature

    Returns the (possibly updated) Payment instance. Raises
    `paypal.PayPalError` if PayPal could not be reached at all
    (network/parse failure) - in that case the payment is left as-is
    (still 'pending') so it can be retried.
    """
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment_id)
        if payment.is_final:
            # Another request (webhook or return_url) already settled
            # this payment while we were waiting for the row lock.
            return payment

        data = paypal.capture_order(payment.paypal_order_id)
        payment.raw_capture_response = data
        status = (data.get('status') or '').upper()

        if status == 'COMPLETED':
            payment.status = 'success'
            payment.paypal_capture_id = paypal.capture_id_from_order(data)
            payment.verified_at = timezone.now()
            payment.failure_reason = ''
            payment.save()
            _activate_subscription(payment)
            return payment

        # Capture can fail because the order was already captured before
        # (e.g. the user hit "back" and returned twice, or the webhook
        # beat the return_url view to it). That's not a real failure -
        # re-fetch the order itself and trust whatever status PayPal
        # reports for it.
        details = data.get('details') or []
        issue = details[0].get('issue') if details else data.get('name')
        if issue == 'ORDER_ALREADY_CAPTURED':
            logger.info('Order already captured tx_ref=%s, re-fetching order state.', payment.tx_ref)
            return _sync_from_order_locked(payment, paypal.get_order(payment.paypal_order_id))

        payment.status = 'failed'
        payment.failure_reason = (
            (details[0].get('description') if details else None)
            or data.get('message')
            or 'Payment could not be completed.'
        )
        payment.save()
        logger.info('Payment failed tx_ref=%s reason=%s', payment.tx_ref, payment.failure_reason)
        return payment


def _sync_from_order_locked(payment: Payment, order_data: dict) -> Payment:
    """Update an already-locked Payment from a GET /v2/checkout/orders/{id}
    response. Internal helper - callers must hold the row lock (i.e. call
    this only from inside `capture_and_sync`/`sync_from_order`'s atomic
    block). Safe to call more than once (idempotent)."""
    payment.raw_capture_response = order_data
    status = (order_data.get('status') or '').upper()

    if status == 'COMPLETED':
        payment.status = 'success'
        payment.paypal_capture_id = paypal.capture_id_from_order(order_data) or payment.paypal_capture_id
        payment.verified_at = timezone.now()
        payment.failure_reason = ''
        payment.save()
        _activate_subscription(payment)
    elif status == 'VOIDED':
        payment.status = 'failed'
        payment.failure_reason = 'Payment was voided.'
        payment.save()
    else:
        # CREATED / APPROVED / PAYER_ACTION_REQUIRED - still pending; the
        # return_url view, a retried webhook, or another verify call will
        # settle it later.
        logger.info('PayPal order still pending tx_ref=%s status=%s', payment.tx_ref, status)

    return payment


def sync_from_order(payment_id: int, order_data: dict) -> Payment:
    """Public entry point for `_sync_from_order_locked` that takes a row
    lock first. Used by the webhook path for event types that only need
    order state confirmed (not captured)."""
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment_id)
        if payment.is_final:
            return payment
        return _sync_from_order_locked(payment, order_data)


def process_webhook_event(event: dict) -> Optional[Payment]:
    """Turn a verified PayPal webhook event body into a Payment update.

    Returns the affected Payment, or None if the event didn't reference a
    Payment we know about (unknown order id) or wasn't an event type we
    act on. Idempotent - replays of the same event are safe. Raises
    `paypal.PayPalError` if PayPal's API could not be reached while
    settling the event (caller should have PayPal retry the webhook
    later in that case).
    """
    event_type = event.get('event_type') or ''
    resource = event.get('resource') or {}

    if event_type.startswith('CHECKOUT.ORDER'):
        order_id = resource.get('id')
    elif event_type.startswith('PAYMENT.CAPTURE'):
        order_id = ((resource.get('supplementary_data') or {}).get('related_ids') or {}).get('order_id')
    else:
        order_id = None

    if not order_id:
        logger.info('Ignoring PayPal webhook event_type=%s (no order id to act on)', event_type)
        return None

    try:
        payment = Payment.objects.get(paypal_order_id=order_id)
    except Payment.DoesNotExist:
        logger.warning('PayPal webhook for unknown order_id=%s', order_id)
        return None

    if payment.is_final:
        # Already settled (likely via the return_url path) - idempotent no-op.
        return payment

    if event_type == 'CHECKOUT.ORDER.APPROVED':
        # The buyer approved but may never come back to our return_url
        # (closed the tab, etc.) - capture here so the payment doesn't
        # get stuck pending forever.
        return capture_and_sync(payment.pk)

    return sync_from_order(payment.pk, paypal.get_order(payment.paypal_order_id))
