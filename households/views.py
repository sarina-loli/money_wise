import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import HouseholdInviteForm
from .models import Household, HouseholdInvite, HouseholdMembership, get_household
import resend
from django.conf import settings
import resend
from django.template.loader import render_to_string
logger = logging.getLogger(__name__)


@login_required
def household_home(request):
    household = get_household(request.user)
    is_owner = bool(household and household.is_owner(request.user))
    # Shown to the owner as a status list (pending/accepted/expired badges) —
    # not filtered to pending-only anymore, so past invites stay visible.
    invites = household.invites.all() if household and is_owner else None
    return render(request, 'households/home.html', {
        'household': household,
        'is_owner': is_owner,
        'invites': invites,
        'members': household.memberships.select_related('user') if household else None,
    })


@login_required
@require_POST
def household_create(request):
    if not request.user.profile.is_family:
        messages.error(request, 'Household sharing is a Family-plan feature. Upgrade to create one.')
        return redirect('core:landing')
    if get_household(request.user):
        messages.info(request, 'You already belong to a household.')
        return redirect('households:home')

    name = request.POST.get('name', '').strip() or f"{request.user.first_name or request.user.username}'s Household"
    household = Household.objects.create(name=name, owner=request.user)
    HouseholdMembership.objects.create(household=household, user=request.user, role='owner')
    messages.success(request, 'Household created — you can now invite up to 4 more members.')
    return redirect('households:home')


@login_required
@require_POST
def household_invite(request):
    """
    Invite a family member by email.
    """
    household = get_household(request.user)

    if not household or not household.is_owner(request.user):
        messages.error(request, "Only the household owner can send invites.")
        return redirect("households:home")

    if not request.user.profile.is_family:
        messages.error(
            request,
            "Your Family subscription looks inactive, so invites are paused. "
            "Check Settings → Plan & Billing.",
        )
        return redirect("households:home")

    if not household.can_add_member():
        messages.error(
            request,
            f"This household is already at the {Household.MAX_MEMBERS}-member limit."
        )
        return redirect("households:home")

    form = HouseholdInviteForm(
        request.POST,
        household=household,
        invited_by=request.user
    )

    if not form.is_valid():
        for error in form.errors.get("email", form.errors.get("__all__", [])):
            messages.error(request, error)
        return redirect("households:home")

    email = form.cleaned_data["email"]

    try:
        invite = HouseholdInvite.objects.create(
            household=household,
            email=email,
            invited_by=request.user,
        )
    except Exception:
        logger.warning(
            "Duplicate/failed invite create for household_id=%s email=%s",
            household.id,
            email,
        )
        messages.error(request, f"An invite is already pending for {email}.")
        return redirect("households:home")

    accept_url = request.build_absolute_uri(
        reverse("households:accept_invite", args=[invite.token])
    )

    context = {
        "household": household,
        "inviter": request.user,
        "accept_url": accept_url,
        "expiry_days": HouseholdInvite.EXPIRY_DAYS,
    }

    try:
        html_body = render_to_string(
            "households/invitation_email.html",
            context,
        )

        text_body = f"""
Hi,

{request.user.get_full_name() or request.user.username} has invited you to join the "{household.name}" family on MoneyWise.

Accept your invitation here:

{accept_url}

This invitation expires in {HouseholdInvite.EXPIRY_DAYS} days.

Thanks,
MoneyWise Team
"""

        resend.Emails.send({
            "from": "onboarding@resend.dev",  # or your verified sender
            "to": [email],
            "subject": f"You're invited to join {household.name} on MoneyWise",
            "html": html_body,
            "text": text_body,
        })

    except Exception:
        logger.exception("Failed to send household invite email to %s", email)
        invite.delete()
        messages.error(
            request,
            "We couldn't send that invite email. Please try again."
        )
        return redirect("households:home")

    messages.success(request, f"Invite sent to {email}.")
    return redirect("households:home")
@login_required
def household_invite_accept(request, token):
    """Accept a household invite. Equivalent of the requested
    `accept_family_invitation` view: validates the token, requires login
    (via `@login_required`), adds the user to the household, marks the
    invite 'accepted', and — via `select_for_update` — can't be used twice
    even if the link is opened in two tabs at once.
    """
    invite = get_object_or_404(HouseholdInvite, token=token)

    if invite.status == HouseholdInvite.STATUS_ACCEPTED:
        messages.info(request, 'This invitation has already been used.')
        return redirect('households:home')

    if invite.status == HouseholdInvite.STATUS_EXPIRED or invite.is_expired:
        if invite.status != HouseholdInvite.STATUS_EXPIRED:
            invite.status = HouseholdInvite.STATUS_EXPIRED
            invite.save(update_fields=['status'])
        messages.error(request, 'This invitation has expired. Ask the household owner to send a new one.')
        return redirect('households:home')

    household = invite.household
    if get_household(request.user):
        messages.error(request, 'You already belong to a household — leave it first to accept a new invite.')
        return redirect('households:home')
    if not household.can_add_member():
        messages.error(request, 'That household is already full.')
        return redirect('households:home')

    with transaction.atomic():
        invite = HouseholdInvite.objects.select_for_update().get(pk=invite.pk)
        if invite.status != HouseholdInvite.STATUS_PENDING:
            # Someone else (or a second tab) already used this invite while
            # we were waiting for the row lock.
            messages.info(request, 'This invitation has already been used.')
            return redirect('households:home')

        HouseholdMembership.objects.create(household=household, user=request.user, role='member')
        invite.status = HouseholdInvite.STATUS_ACCEPTED
        invite.accepted_at = timezone.now()
        invite.save(update_fields=['status', 'accepted_at'])

    messages.success(request, f'You joined {household.name}!')
    return redirect('households:home')


@login_required
@require_POST
def household_remove_member(request, user_id):
    household = get_household(request.user)
    if not household or not household.is_owner(request.user):
        messages.error(request, 'Only the household owner can remove members.')
        return redirect('households:home')
    if int(user_id) == request.user.id:
        messages.error(request, "Use 'Disband Household' to remove yourself as owner.")
        return redirect('households:home')

    membership = get_object_or_404(HouseholdMembership, household=household, user_id=user_id)
    membership.delete()
    messages.success(request, 'Member removed from the household.')
    return redirect('households:home')


@login_required
@require_POST
def household_leave(request):
    household = get_household(request.user)
    if not household:
        messages.error(request, "You're not in a household.")
        return redirect('households:home')
    if household.is_owner(request.user):
        messages.error(request, 'As the owner, use "Disband Household" instead of leaving.')
        return redirect('households:home')

    request.user.household_membership.delete()
    messages.success(request, 'You left the household.')
    return redirect('households:home')


@login_required
@require_POST
def household_disband(request):
    household = get_household(request.user)
    if not household or not household.is_owner(request.user):
        messages.error(request, 'Only the household owner can disband it.')
        return redirect('households:home')
    household.delete()  # cascades memberships; shared budgets keep their own owner, just unshared
    messages.success(request, 'Household disbanded.')
    return redirect('households:home')
