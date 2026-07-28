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
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import paypal, paypal_service
from .models import Payment
from .plans import PLAN_PRICES_USD

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


# ---------------------------------------------------------------------------
# Checkout — start a payment
# ---------------------------------------------------------------------------

@login_required
@require_POST
def create_checkout_session(request, plan):
    """Starts a real PayPal payment for the Pro or Family plan.

    Flow:
      1. Validate the plan and the user's email.
      2. Ask PayPal (via `paypal_service.start_checkout`) to create a
         pending Payment row and a matching PayPal order.
      3. Redirect the user's browser to PayPal's hosted checkout
         ("approve") page.

    All Payment-row bookkeeping, duplicate-checkout prevention, and the
    actual PayPal API call live in `billing/paypal_service.py` — this view
    only handles the HTTP request/response and turns errors into a
    friendly message.
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

    return_url = _absolute_url(request, 'billing:payment_return')
    # PayPal sends the browser to cancel_url (unchanged) if the buyer backs
    # out of checkout, and to return_url if they approve. We reuse the same
    # view for both and tell them apart with this flag rather than standing
    # up a second URL/view.
    cancel_url = f'{return_url}?cancelled=1'

    try:
        payment = paypal_service.start_checkout(
            user=request.user, plan=plan, email=email,
            return_url=return_url, cancel_url=cancel_url,
        )
    except paypal_service.DuplicateCheckoutError as exc:
        messages.warning(request, str(exc))
        return redirect(reverse('core:landing') + '#pricing')
    except paypal.PayPalError as exc:
        messages.error(request, f"We couldn't start your payment: {exc}")
        return redirect(reverse('core:landing') + '#pricing')

    return redirect(payment.checkout_url)


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
    PayPal's API first, via `paypal_service.capture_and_sync`.
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
            payment = paypal_service.capture_and_sync(payment.pk)
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
      - Even a validly-signed payload is NOT trusted directly —
        `paypal_service.process_webhook_event` re-fetches the order from
        PayPal's API before touching the database.
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

    try:
        paypal_service.process_webhook_event(event)
    except paypal.PayPalError as exc:
        logger.error('Webhook capture/verify failed: %s', exc)
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
    paypal_service.downgrade_to_free(request.user.profile)
    messages.info(request, 'Your plan is back to Free.')
    return redirect('accounts:settings')
