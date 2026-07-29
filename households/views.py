from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from finance.models import Notification
from .models import Household, HouseholdInvite, HouseholdMembership, get_household


@login_required
def household_home(request):
    household = get_household(request.user)
    is_owner = bool(household and household.is_owner(request.user))
    pending_invites = household.invites.filter(accepted=False) if household and is_owner else None
    return render(request, 'households/home.html', {
        'household': household,
        'is_owner': is_owner,
        'pending_invites': pending_invites,
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
    household = get_household(request.user)
    if not household or not household.is_owner(request.user):
        messages.error(request, 'Only the household owner can send invites.')
        return redirect('households:home')
    if not request.user.profile.is_family:
        messages.error(
            request,
            'Your Family subscription looks inactive, so invites are paused. '
            'Check Settings → Plan & Billing.',
        )
        return redirect('households:home')
    if not household.can_add_member():
        messages.error(request, f'This household is already at the {Household.MAX_MEMBERS}-member limit.')
        return redirect('households:home')

    email = request.POST.get('email', '').strip().lower()
    if not email:
        messages.error(request, 'Enter an email address to invite.')
        return redirect('households:home')

    invited_user = User.objects.filter(email__iexact=email).first()
    if not invited_user:
        messages.error(request, f'No MoneyWise account was found for {email}. They need to sign up first.')
        return redirect('households:home')
    if invited_user.id == request.user.id:
        messages.error(request, "You can't invite yourself.")
        return redirect('households:home')

    invite = HouseholdInvite.objects.create(household=household, email=email, invited_by=request.user)
    accept_url = request.build_absolute_uri(reverse('households:accept_invite', args=[invite.token]))

    Notification.objects.create(
        user=invited_user,
        type='household_invite',
        title=f'Invitation to join {household.name}',
        message=(
            f'{request.user.get_full_name() or request.user.username} invited you to join '
            f'their household "{household.name}" on MoneyWise.'
        ),
        link_url=accept_url,
    )
    messages.success(request, f'Invite sent to {email} as an in-app notification.')
    return redirect('households:home')


@login_required
def household_invite_accept(request, token):
    invite = get_object_or_404(HouseholdInvite, token=token, accepted=False)
    household = invite.household

    if get_household(request.user):
        messages.error(request, 'You already belong to a household — leave it first to accept a new invite.')
        return redirect('households:home')
    if not household.can_add_member():
        messages.error(request, 'That household is already full.')
        return redirect('households:home')

    HouseholdMembership.objects.create(household=household, user=request.user, role='member')
    invite.accepted = True
    invite.save(update_fields=['accepted'])

    # Clear the in-app notification that pointed here, if any (does nothing if none exists).
    Notification.objects.filter(
        user=request.user,
        type='household_invite',
        is_read=False,
        link_url__icontains=reverse('households:accept_invite', args=[token]),
    ).update(is_read=True)

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
