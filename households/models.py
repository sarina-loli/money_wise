import secrets
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


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
    STATUS_PENDING = 'pending'
    STATUS_ACCEPTED = 'accepted'
    STATUS_EXPIRED = 'expired'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACCEPTED, 'Accepted'),
        (STATUS_EXPIRED, 'Expired'),
    ]

    # How long an invite link stays valid before accept_family_invitation
    # (household_invite_accept) starts rejecting it.
    EXPIRY_DAYS = 7

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name='invites')
    email = models.EmailField()
    token = models.CharField(max_length=64, unique=True, default=secrets.token_urlsafe)
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_invites')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        # A household can only have ONE live (pending) invite per email at
        # a time — this is what makes duplicate invites impossible at the
        # database level, not just in view-level validation.
        constraints = [
            models.UniqueConstraint(
                fields=['household', 'email'],
                condition=models.Q(status='pending'),
                name='unique_pending_invite_per_email',
            ),
        ]

    def __str__(self):
        return f'Invite for {self.email} to {self.household.name} ({self.status})'

    @property
    def is_expired(self):
        """True once a pending invite has passed EXPIRY_DAYS — checked
        lazily on access (return_url-style pattern), since a scheduled
        job to sweep these isn't set up yet."""
        return self.status == self.STATUS_PENDING and timezone.now() > self.created_at + timedelta(days=self.EXPIRY_DAYS)


def get_household(user):
    """Returns the Household a user belongs to (as owner or member), or None."""
    if not user.is_authenticated:
        return None
    try:
        return user.household_membership.household
    except HouseholdMembership.DoesNotExist:
        return None
