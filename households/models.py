import secrets

from django.contrib.auth.models import User
from django.db import models


class Household(models.Model):
    """A Family-plan group. The owner must be on an active Family
    subscription to invite new members or share budgets."""

    MAX_MEMBERS = 5

    name = models.CharField(max_length=120, default='My Household')
    owner = models.OneToOneField(User, on_delete=models.CASCADE, related_name='owned_household')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def member_count(self):
        return self.memberships.count()

    def can_add_member(self):
        return self.member_count() < self.MAX_MEMBERS

    def is_owner(self, user):
        return self.owner_id == user.id


class HouseholdMembership(models.Model):
    ROLE_CHOICES = [('owner', 'Owner'), ('member', 'Member')]

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name='memberships')
    # A user can belong to at most one household at a time.
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='household_membership')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['joined_at']

    def __str__(self):
        return f'{self.user.username} in {self.household.name} ({self.role})'


class HouseholdInvite(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name='invites')
    email = models.EmailField()
    token = models.CharField(max_length=64, unique=True, default=secrets.token_urlsafe)
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_invites')
    accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Invite for {self.email} to {self.household.name}'


def get_household(user):
    """Returns the Household a user belongs to (as owner or member), or None."""
    if not user.is_authenticated:
        return None
    try:
        return user.household_membership.household
    except HouseholdMembership.DoesNotExist:
        return None
