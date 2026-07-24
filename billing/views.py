from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from .plans import TRIAL_DAYS

# NOTE: This app no longer talks to Stripe (or any payment processor) at
# all. "Starting a plan" just flips the user's Profile into a free trial
# for TRIAL_DAYS days — no card, no checkout session, no real charge.
# When you're ready to accept real payments again, re-introduce a
# provider here (Stripe, Paddle, etc.) behind this same create_checkout_session
# view so the templates/urls don't need to change.


@login_required
@require_POST
def create_checkout_session(request, plan):
    """Activates a free trial of the Pro or Family plan for the current
    user. No payment method is collected and no money moves."""
    if plan not in ('pro', 'family'):
        messages.error(request, "That isn't a plan you can start a trial for.")
        return redirect('core:landing')

    profile = request.user.profile

    if profile.plan == plan and profile.subscription_status in ('active', 'trialing'):
        messages.info(request, f"You're already on the {profile.get_plan_display()} plan.")
        return redirect('finance:dashboard')

    profile.plan = plan
    profile.subscription_status = 'trialing'
    profile.current_period_end = timezone.now() + timedelta(days=TRIAL_DAYS)
    # Any old Stripe identifiers are irrelevant now that this is a local trial.
    profile.stripe_customer_id = ''
    profile.stripe_subscription_id = ''
    profile.save(update_fields=[
        'plan', 'subscription_status', 'current_period_end',
        'stripe_customer_id', 'stripe_subscription_id',
    ])

    messages.success(
        request,
        f"Your {TRIAL_DAYS}-day free trial of the "
        f"{profile.get_plan_display()} plan has started — no payment required.",
    )
    return redirect('billing:checkout_success')


@login_required
def checkout_success(request):
    messages.success(request, 'Your plan is active. Enjoy your free trial!')
    return redirect('finance:dashboard')


@login_required
def checkout_cancel(request):
    messages.info(request, "No trial was started — you weren't charged anything.")
    return redirect('core:landing')


@login_required
@require_POST
def billing_portal(request):
    """Lets a user end their trial and drop back to the Free plan.
    There's no real subscription to manage since nothing was ever
    charged, so this just resets their plan locally."""
    profile = request.user.profile
    profile.plan = 'free'
    profile.subscription_status = ''
    profile.current_period_end = None
    profile.save(update_fields=['plan', 'subscription_status', 'current_period_end'])
    messages.info(request, 'Your trial has ended and your plan is back to Free.')
    return redirect('accounts:settings')
