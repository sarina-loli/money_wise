"""Tests for the PayPal checkout, return, and webhook flow.

These mock every call into `billing/paypal.py` (the module that actually
talks to PayPal over HTTP) so the tests exercise our own logic —
Payment bookkeeping, subscription activation, idempotency — without
making real network calls or needing live sandbox credentials.
"""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from .models import Payment
from . import paypal


def _order_response(order_id='ORDER123', status='CREATED', approve_url='https://paypal.test/approve'):
    return {
        'id': order_id,
        'status': status,
        'links': [{'rel': 'approve', 'href': approve_url}],
    }


def _capture_response(order_id='ORDER123', capture_id='CAP123', status='COMPLETED'):
    return {
        'id': order_id,
        'status': status,
        'purchase_units': [{'payments': {'captures': [{'id': capture_id}]}}],
    }


class CheckoutSessionTests(TestCase):
    """POST /billing/checkout/<plan>/ — starts a payment and redirects to
    PayPal's approve URL."""

    def setUp(self):
        self.user = User.objects.create_user('alice', 'alice@example.com', 'pw12345')
        self.client = Client()
        self.client.force_login(self.user)

    @patch('billing.paypal.create_order')
    def test_sandbox_checkout_creates_pending_payment_and_redirects_to_approve_url(self, mock_create):
        mock_create.return_value = _order_response()

        response = self.client.post(reverse('billing:checkout', args=['pro']))

        payment = Payment.objects.get(user=self.user, plan='pro')
        self.assertEqual(payment.status, 'pending')
        self.assertEqual(payment.paypal_order_id, 'ORDER123')
        self.assertEqual(payment.checkout_url, 'https://paypal.test/approve')
        self.assertRedirects(response, 'https://paypal.test/approve', fetch_redirect_response=False)

    @patch('billing.paypal.create_order')
    def test_double_submit_does_not_create_a_second_pending_payment(self, mock_create):
        mock_create.return_value = _order_response()
        self.client.post(reverse('billing:checkout', args=['pro']))
        self.assertEqual(mock_create.call_count, 1)

        # Second click before the first checkout resolves — should be
        # blocked rather than creating a duplicate order.
        response = self.client.post(reverse('billing:checkout', args=['pro']), follow=True)

        self.assertEqual(Payment.objects.filter(user=self.user, plan='pro').count(), 1)
        self.assertEqual(mock_create.call_count, 1)

    @patch('billing.paypal.create_order')
    def test_paypal_error_marks_payment_failed_and_shows_message(self, mock_create):
        mock_create.side_effect = paypal.PayPalError('Payment could not be started. Please try again.')

        response = self.client.post(reverse('billing:checkout', args=['pro']), follow=True)

        payment = Payment.objects.get(user=self.user, plan='pro')
        self.assertEqual(payment.status, 'failed')
        self.assertContains(response, "couldn&#x27;t start your payment")

    def test_invalid_plan_is_rejected(self):
        response = self.client.post(reverse('billing:checkout', args=['ultra']), follow=True)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertContains(response, "isn&#x27;t a plan")


class PaymentReturnTests(TestCase):
    """GET /billing/payment/return/ — captures the order and activates the plan."""

    def setUp(self):
        self.user = User.objects.create_user('bob', 'bob@example.com', 'pw12345')
        self.client = Client()
        self.client.force_login(self.user)
        self.payment = Payment.objects.create(
            user=self.user, plan='pro', tx_ref='mw-1-abc', amount='9.00',
            currency='USD', status='pending', email=self.user.email,
            paypal_order_id='ORDER123',
        )

    @patch('billing.paypal.capture_order')
    def test_successful_capture_activates_subscription_and_updates_history(self, mock_capture):
        mock_capture.return_value = _capture_response()

        response = self.client.get(reverse('billing:payment_return'), {'token': 'ORDER123'})

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'success')
        self.assertEqual(self.payment.paypal_capture_id, 'CAP123')
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.plan, 'pro')
        self.assertTrue(self.user.profile.has_active_subscription)
        self.assertTemplateUsed(response, 'billing/checkout_success.html')

        # Payment history reflects the completed payment.
        history = self.client.get(reverse('billing:history'))
        self.assertContains(history, self.payment.tx_ref)

    @patch('billing.paypal.capture_order')
    def test_browser_refresh_after_success_does_not_double_capture(self, mock_capture):
        mock_capture.return_value = _capture_response()
        self.client.get(reverse('billing:payment_return'), {'token': 'ORDER123'})
        self.assertEqual(mock_capture.call_count, 1)

        # Refreshing the return_url page again should be a no-op — the
        # Payment is already final, so capture_order must not be called again.
        response = self.client.get(reverse('billing:payment_return'), {'token': 'ORDER123'})

        self.assertEqual(mock_capture.call_count, 1)
        self.assertTemplateUsed(response, 'billing/checkout_success.html')

    @patch('billing.paypal.get_order')
    @patch('billing.paypal.capture_order')
    def test_already_captured_order_falls_back_to_get_order(self, mock_capture, mock_get):
        mock_capture.return_value = {
            'name': 'UNPROCESSABLE_ENTITY',
            'details': [{'issue': 'ORDER_ALREADY_CAPTURED'}],
        }
        mock_get.return_value = _capture_response()

        self.client.get(reverse('billing:payment_return'), {'token': 'ORDER123'})

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'success')
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.has_active_subscription)

    @patch('billing.paypal.capture_order')
    def test_declined_payment_is_marked_failed(self, mock_capture):
        mock_capture.return_value = {
            'status': 'VOIDED',
            'details': [{'description': 'Card declined.'}],
        }

        response = self.client.get(reverse('billing:payment_return'), {'token': 'ORDER123'})

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'failed')
        self.assertEqual(self.payment.failure_reason, 'Card declined.')
        self.assertTemplateUsed(response, 'billing/checkout_failed.html')
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.plan, 'free')

    def test_cancelled_checkout_is_marked_failed_without_calling_paypal(self):
        with patch('billing.paypal.capture_order') as mock_capture:
            response = self.client.get(
                reverse('billing:payment_return'), {'token': 'ORDER123', 'cancelled': '1'},
            )
            mock_capture.assert_not_called()

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'failed')
        self.assertEqual(self.payment.failure_reason, 'Payment was cancelled.')
        self.assertTemplateUsed(response, 'billing/checkout_failed.html')

    @patch('billing.paypal.capture_order')
    def test_paypal_unreachable_leaves_payment_pending_for_retry(self, mock_capture):
        mock_capture.side_effect = paypal.PayPalError('Could not reach the payment provider. Please try again.')

        response = self.client.get(reverse('billing:payment_return'), {'token': 'ORDER123'})

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'pending')
        self.assertTemplateUsed(response, 'billing/checkout_pending.html')


class PaypalWebhookTests(TestCase):
    """POST /billing/webhook/paypal/ — server-to-server confirmation, used
    as a safety net if the buyer never returns to payment_return."""

    def setUp(self):
        self.user = User.objects.create_user('carol', 'carol@example.com', 'pw12345')
        self.payment = Payment.objects.create(
            user=self.user, plan='family', tx_ref='mw-2-xyz', amount='19.00',
            currency='USD', status='pending', email=self.user.email,
            paypal_order_id='ORDER999',
        )
        self.client = Client()

    def _post_event(self, event):
        import json
        return self.client.post(
            reverse('billing:paypal_webhook'),
            data=json.dumps(event),
            content_type='application/json',
        )

    def test_unverified_signature_is_rejected(self):
        with patch('billing.paypal.verify_webhook_signature', return_value=False):
            response = self._post_event({'event_type': 'CHECKOUT.ORDER.APPROVED', 'resource': {'id': 'ORDER999'}})
        self.assertEqual(response.status_code, 400)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'pending')

    @patch('billing.paypal.capture_order')
    def test_order_approved_event_captures_and_activates(self, mock_capture):
        mock_capture.return_value = _capture_response(order_id='ORDER999')
        with patch('billing.paypal.verify_webhook_signature', return_value=True):
            response = self._post_event({'event_type': 'CHECKOUT.ORDER.APPROVED', 'resource': {'id': 'ORDER999'}})

        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'success')
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.plan, 'family')

    @patch('billing.paypal.capture_order')
    def test_retried_webhook_does_not_double_capture(self, mock_capture):
        mock_capture.return_value = _capture_response(order_id='ORDER999')
        with patch('billing.paypal.verify_webhook_signature', return_value=True):
            self._post_event({'event_type': 'CHECKOUT.ORDER.APPROVED', 'resource': {'id': 'ORDER999'}})
            # PayPal retries webhooks that don't get a prompt 200, or just
            # sends the same event twice — either way this must be a no-op.
            self._post_event({'event_type': 'CHECKOUT.ORDER.APPROVED', 'resource': {'id': 'ORDER999'}})

        self.assertEqual(mock_capture.call_count, 1)

    def test_unknown_order_id_is_acknowledged_without_error(self):
        with patch('billing.paypal.verify_webhook_signature', return_value=True):
            response = self._post_event({'event_type': 'CHECKOUT.ORDER.APPROVED', 'resource': {'id': 'NOT-A-REAL-ORDER'}})
        self.assertEqual(response.status_code, 200)

    @patch('billing.paypal.capture_order')
    def test_webhook_after_return_url_already_settled_is_a_no_op(self, mock_capture):
        # Simulate the return_url path having already captured this payment.
        self.payment.status = 'success'
        self.payment.save(update_fields=['status'])

        with patch('billing.paypal.verify_webhook_signature', return_value=True):
            self._post_event({'event_type': 'CHECKOUT.ORDER.APPROVED', 'resource': {'id': 'ORDER999'}})

        mock_capture.assert_not_called()
