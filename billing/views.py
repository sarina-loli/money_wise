import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import paypal
from .models import Payment
from .plans import PLAN_NAMES, PLAN_PRICES_USD

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _absolute_url(request, name, *args):
    """Build a fully-qualified https?://host/... URL for a named route.
    PayPal needs real, internet-reachable URLs for return_url/cancel_url —
    relative paths won't work since PayPal's servers/redirects use these
    directly, and the webhook is called by PayPal's servers independent of
    any browser."""
    return request.build_absolute_uri(reverse(name, args=args))


def _apply_successful_payment(payment):
    """Grant the plan to the user once a payment is confirmed successful.
    Safe to call more than once (idempotent) — re-applying the same plan
    to the same profile is a no-op in effect."""
    profile = payment.user.profile
    profile.plan = payment.plan
    profile.subscription_status = 'active'
    profile.current_period_end = timezone.now() + timezone.timedelta(days=30)
    profile.save(update_fields=['plan', 'subscription_status', 'current_period_end'])
    logger.info(
        'Activated plan=%s for user_id=%s via tx_ref=%s',
        payment.plan, payment.user_id, payment.tx_ref,
    )


def _capture_and_sync(payment):
    """Capture the PayPal order for this Payment (this is the call that
    actually moves the money) and update the local row to match. This is
    the ONLY place that is allowed to mark a Payment 'success' from a fresh
    capture — never trust a redirect query string or a webhook body on its
    own, always confirm with PayPal's API first, per PayPal's own guidance:
    https://developer.paypal.com/docs/api/webhooks/v1/#verify-webhook-signature

    Returns the (possibly updated) Payment instance. Raises
    paypal.PayPalError if PayPal could not be reached at all (network/parse
    failure) — in that case the payment is left as-is (still 'pending') so
    it can be retried.
    """
    data = paypal.capture_order(payment.paypal_order_id)
    payment.raw_capture_response = data
    status = (data.get('status') or '').upper()

    if status == 'COMPLETED':
        payment.status = 'success'
        payment.paypal_capture_id = paypal.capture_id_from_order(data)
        payment.verified_at = timezone.now()
        payment.failure_reason = ''
        payment.save()
        _apply_successful_payment(payment)
        return payment

    # Capture can fail because the order was already captured before (e.g.
    # the user hit "back" and returned twice, or the webhook beat the
    # return_url view to it). That's not a real failure — re-fetch the
    # order itself and trust whatever status PayPal reports for it.
    details = data.get('details') or []
    issue = details[0].get('issue') if details else data.get('name')
    if issue == 'ORDER_ALREADY_CAPTURED':
        logger.info('Order already captured tx_ref=%s, re-fetching order state.', payment.tx_ref)
        return _sync_from_order(payment, paypal.get_order(payment.paypal_order_id))

    payment.status = 'failed'
    payment.failure_reason = (
        (details[0].get('description') if details else None)
        or data.get('message')
        or 'Payment could not be completed.'
    )
    payment.save()
    logger.info('Payment failed tx_ref=%s reason=%s', payment.tx_ref, payment.failure_reason)
    return payment


def _sync_from_order(payment, order_data):
    """Update a Payment from a GET /v2/checkout/orders/{id} response. Used
    by the webhook (which never captures money itself, only confirms state)
    and as a fallback when a capture attempt reports the order was already
    captured elsewhere. Safe to call more than once (idempotent)."""
    payment.raw_capture_response = order_data
    status = (order_data.get('status') or '').upper()

    if status == 'COMPLETED':
        payment.status = 'success'
        payment.paypal_capture_id = paypal.capture_id_from_order(order_data) or payment.paypal_capture_id
        payment.verified_at = timezone.now()
        payment.failure_reason = ''
        payment.save()
        _apply_successful_payment(payment)
    elif status == 'VOIDED':
        payment.status = 'failed'
        payment.failure_reason = 'Payment was voided.'
        payment.save()
    else:
        # CREATED / APPROVED / PAYER_ACTION_REQUIRED — still pending; the
        # return_url view, a retried webhook, or another verify call will
        # settle it later.
        logger.info('PayPal order still pending tx_ref=%s status=%s', payment.tx_ref, status)

    return payment


# ---------------------------------------------------------------------------
# Checkout — start a payment
# ---------------------------------------------------------------------------

@login_required
@require_POST
def create_checkout_session(request, plan):
    """Starts a real PayPal payment for the Pro or Family plan.

    Flow:
      1. Validate the plan and build a Payment(status='pending') row.
      2. Ask PayPal to create an order (SANDBOX MODE — uses whichever
         credentials are configured in PAYPAL_CLIENT_ID/SECRET; see
         .env.example).
      3. Redirect the user's browser to PayPal's hosted checkout
         ("approve") page.
    """
    if plan not in PLAN_PRICES_USD:
        messages.error(request, "That isn't a plan you can subscribe to.")
        return redirect('core:landing')

    profile = request.user.profile
    if profile.plan == plan and profile.has_active_subscription:
        messages.info(request, f"You're already on the {profile.get_plan_display()} plan.")
        return redirect('finance:dashboard')

    # --- Input validation -------------------------------------------------
    email = (request.user.email or '').strip()
    if not email:
        messages.error(
            request,
            'Your account needs a valid email address on file before you can '
            'subscribe. Please add one in Settings and try again.',
        )
        return redirect('accounts:settings')
    try:
        validate_email(email)
    except ValidationError:
        messages.error(request, 'Your account email address looks invalid. Please update it and try again.')
        return redirect('accounts:settings')

    amount = PLAN_PRICES_USD[plan]
    tx_ref = paypal.generate_tx_ref(prefix=f'mw-{request.user.id}')

    payment = Payment.objects.create(
        user=request.user,
        plan=plan,
        tx_ref=tx_ref,
        amount=amount,
        currency='USD',
        status='pending',
        email=email,
    )

    return_url = _absolute_url(request, 'billing:payment_return')
    # PayPal sends the browser to cancel_url (unchanged) if the buyer backs
    # out of checkout, and to return_url if they approve. We reuse the same
    # view for both and tell them apart with this flag rather than standing
    # up a second URL/view.
    cancel_url = f'{return_url}?cancelled=1'

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
        logger.warning('Checkout create order failed for user_id=%s tx_ref=%s: %s', request.user.id, tx_ref, exc)
        messages.error(request, f"We couldn't start your payment: {exc}")
        return redirect(reverse('core:landing') + '#pricing')

    approve_url = next((l.get('href') for l in data.get('links', []) if l.get('rel') == 'approve'), '')
    payment.paypal_order_id = data.get('id', '')
    payment.checkout_url = approve_url
    payment.raw_create_response = data
    payment.save(update_fields=['paypal_order_id', 'checkout_url', 'raw_create_response', 'updated_at'])

    logger.info('Checkout started user_id=%s plan=%s tx_ref=%s order_id=%s', request.user.id, plan, tx_ref, payment.paypal_order_id)
    return redirect(approve_url)


# ---------------------------------------------------------------------------
# Return URL — user's browser lands here after leaving PayPal's checkout
# ---------------------------------------------------------------------------

@login_required
@require_GET
def payment_return(request):
    """RETURN_URL / CANCEL_URL target. PayPal sends the user's browser back
    here (appending ?token=<order_id>&PayerID=... on approval) after they
    finish on the hosted checkout page. On cancellation it hits the same
    view via our own `?cancelled=1` flag on cancel_url (see
    create_checkout_session).

    This view is what actually CAPTURES the order (moves the money) — it
    never trusts the querystring alone; capture/verify always goes back to
    PayPal's API first.
    """
    token = request.GET.get('token')
    cancelled = request.GET.get('cancelled') == '1'

    if not token:
        messages.error(request, "We couldn't find that payment. Please try again.")
        return redirect(reverse('core:landing') + '#pricing')

    payment = get_object_or_404(Payment, paypal_order_id=token)
    if payment.user_id != request.user.id and not request.user.is_staff:
        messages.error(request, "That payment doesn't belong to your account.")
        return redirect('finance:dashboard')

    if cancelled:
        if not payment.is_final:
            payment.status = 'failed'
            payment.failure_reason = 'Payment was cancelled.'
            payment.save(update_fields=['status', 'failure_reason', 'updated_at'])
        return render(request, 'billing/checkout_failed.html', {'payment': payment})

    if not payment.is_final:
        try:
            _capture_and_sync(payment)
        except paypal.PayPalError as exc:
            logger.error('Could not capture/verify tx_ref=%s on return: %s', payment.tx_ref, exc)
            messages.warning(
                request,
                "We couldn't confirm your payment status right away. "
                "If the money left your account, your plan will update "
                "automatically within a few minutes.",
            )
            return render(request, 'billing/checkout_pending.html', {'payment': payment})

    if payment.status == 'success':
        return render(request, 'billing/checkout_success.html', {'payment': payment})
    elif payment.status == 'failed':
        return render(request, 'billing/checkout_failed.html', {'payment': payment})
    else:
        return render(request, 'billing/checkout_pending.html', {'payment': payment})


# ---------------------------------------------------------------------------
# Webhook — server-to-server notification from PayPal
# ---------------------------------------------------------------------------

@csrf_exempt
@require_POST
def paypal_webhook(request):
    """Webhook target, configured in the PayPal dashboard / sandbox app
    against a Webhooks subscription for this URL. PayPal's servers POST
    here directly, independent of the user's browser — this is what makes
    the integration reliable even if the user closes their browser before
    returning to the site (e.g. after approving on PayPal but never coming
    back, in which case this is the only place that ever calls capture).

    Security:
      - CSRF is exempt because this is called by PayPal's server, not a
        browser with our session/cookies.
      - The request is authenticated using PayPal's Verify Webhook
        Signature API (needs PAYPAL_WEBHOOK_ID), verified in
        billing/paypal.py:verify_webhook_signature.
      - Even a validly-signed payload is NOT trusted directly — we still
        re-fetch the order from PayPal's API before touching the database.
      - Processing is idempotent: replays of the same event are safe.

    Always returns 200 once the event is acknowledged, so PayPal doesn't
    keep retrying. Returns a non-200 only when we could genuinely not
    process the request (bad signature, unreachable PayPal API) so
    PayPal's retry mechanism has a chance to succeed later.
    """
    raw_body = request.body
    signature_ok = paypal.verify_webhook_signature(
        webhook_id=settings.PAYPAL_WEBHOOK_ID,
        headers=request.headers,
        raw_body=raw_body,
    )
    if not signature_ok:
        logger.warning('Rejected PayPal webhook with invalid/missing signature.')
        return HttpResponseBadRequest('invalid signature')

    try:
        event = json.loads(raw_body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        logger.warning('Rejected PayPal webhook with unparsable body.')
        return HttpResponseBadRequest('invalid payload')

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
        return JsonResponse({'received': True})

    try:
        payment = Payment.objects.get(paypal_order_id=order_id)
    except Payment.DoesNotExist:
        logger.warning('PayPal webhook for unknown order_id=%s', order_id)
        return JsonResponse({'received': True})

    if payment.is_final:
        # Already settled (likely via the return_url path) — idempotent no-op.
        return JsonResponse({'received': True, 'already_processed': True})

    try:
        if event_type == 'CHECKOUT.ORDER.APPROVED':
            # The buyer approved but may never come back to our return_url
            # (closed the tab, etc.) — capture here so the payment doesn't
            # get stuck pending forever.
            _capture_and_sync(payment)
        else:
            _sync_from_order(payment, paypal.get_order(payment.paypal_order_id))
    except paypal.PayPalError as exc:
        logger.error('Webhook capture/verify failed for order_id=%s: %s', order_id, exc)
        # 500 so PayPal retries this webhook later.
        return JsonResponse({'received': False, 'error': 'verify_failed'}, status=500)

    return JsonResponse({'received': True})


# ---------------------------------------------------------------------------
# Payment history & subscription management
# ---------------------------------------------------------------------------

@login_required
def payment_history(request):
    payments = request.user.payments.all()[:50]
    return render(request, 'billing/payment_history.html', {'payments': payments})


@login_required
@require_POST
def billing_portal(request):
    """Lets a user drop back to the Free plan. PayPal's sandbox test flow
    has no recurring-subscription object to cancel server-side for these
    one-off Orders payments, so this simply resets the local plan flag —
    the same behaviour as before payments were wired up."""
    profile = request.user.profile
    profile.plan = 'free'
    profile.subscription_status = ''
    profile.current_period_end = None
    profile.save(update_fields=['plan', 'subscription_status', 'current_period_end'])
    messages.info(request, 'Your plan is back to Free.')
    return redirect('accounts:settings')
