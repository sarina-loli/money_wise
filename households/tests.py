from django.contrib.auth.models import User
from django.core import mail
from django.test import Client, TestCase
from django.urls import reverse

from .models import Household, HouseholdInvite, HouseholdMembership


def _make_family_user(username, email):
    user = User.objects.create_user(username, email, 'pw12345')
    user.profile.plan = 'family'
    user.profile.subscription_status = 'active'
    user.profile.save(update_fields=['plan', 'subscription_status'])
    return user


class HouseholdInviteFlowTests(TestCase):
    def setUp(self):
        self.owner = _make_family_user('owner', 'owner@example.com')
        self.client = Client()
        self.client.force_login(self.owner)
        self.client.post(reverse('households:create'), {'name': 'The Test Household'})
        self.household = Household.objects.get(owner=self.owner)

    def test_invite_creates_pending_invite_and_sends_email(self):
        response = self.client.post(reverse('households:invite'), {'email': 'friend@example.com'}, follow=True)

        invite = HouseholdInvite.objects.get(household=self.household, email='friend@example.com')
        self.assertEqual(invite.status, 'pending')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('friend@example.com', mail.outbox[0].to)
        self.assertIn(invite.token, mail.outbox[0].alternatives[0][0])  # HTML body has the accept link

    def test_duplicate_invite_to_same_email_is_rejected(self):
        self.client.post(reverse('households:invite'), {'email': 'friend@example.com'})
        self.client.post(reverse('households:invite'), {'email': 'friend@example.com'})

        self.assertEqual(
            HouseholdInvite.objects.filter(household=self.household, email='friend@example.com').count(), 1,
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_non_owner_cannot_send_invite(self):
        member = _make_family_user('member', 'member@example.com')
        HouseholdMembership.objects.create(household=self.household, user=member, role='member')
        client = Client()
        client.force_login(member)

        client.post(reverse('households:invite'), {'email': 'friend@example.com'})

        self.assertFalse(HouseholdInvite.objects.filter(household=self.household).exists())

    def test_accept_invite_adds_member_and_marks_accepted(self):
        self.client.post(reverse('households:invite'), {'email': 'friend@example.com'})
        invite = HouseholdInvite.objects.get(household=self.household, email='friend@example.com')

        friend = User.objects.create_user('friend', 'friend@example.com', 'pw12345')
        friend_client = Client()
        friend_client.force_login(friend)
        friend_client.get(reverse('households:accept_invite', args=[invite.token]))

        invite.refresh_from_db()
        self.assertEqual(invite.status, 'accepted')
        self.assertIsNotNone(invite.accepted_at)
        self.assertTrue(HouseholdMembership.objects.filter(household=self.household, user=friend).exists())

    def test_accepting_the_same_invite_twice_is_a_no_op_the_second_time(self):
        self.client.post(reverse('households:invite'), {'email': 'friend@example.com'})
        invite = HouseholdInvite.objects.get(household=self.household, email='friend@example.com')

        friend = User.objects.create_user('friend', 'friend@example.com', 'pw12345')
        friend_client = Client()
        friend_client.force_login(friend)
        friend_client.get(reverse('households:accept_invite', args=[invite.token]))

        # Second click on the same link/email — must not create a second membership.
        friend_client.get(reverse('households:accept_invite', args=[invite.token]))

        self.assertEqual(HouseholdMembership.objects.filter(household=self.household, user=friend).count(), 1)
