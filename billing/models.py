from django.contrib.auth.models import User
from django.db import models


class Payment(models.Model):
    """One row per PayPal order/payment attempt (pending, successful, or failed).

    This is the local source of truth for what happened with a payment.
    Every checkout creates a row here *before* we ever talk to PayPal, and
    the row is updated in two independent places once PayPal confirms the
    result:

      1. The user's browser lands back on RETURN_URL (billing:payment_return)
         after approving (or cancelling) on PayPal's checkout page. This is
         also where the order is actually *captured* (money moved).
      2. PayPal's server calls our webhook (billing:paypal_webhook) directly,
         independent of the user's browser — this is the safety net in case
         the user closes their browser before returning to the site.

    Both paths re-fetch the order from PayPal's Get Order API before
    trusting anything, and both paths are safe to run more than once
    (idempotent) since the same order id/status combination is just written
    again.
    """

    PLAN_CHOICES = [
        ('pro', 'Pro'),
        ('family', 'Family'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),      # created locally, user sent to PayPal
        ('success', 'Success'),      # captured successfully with PayPal
        ('failed', 'Failed'),        # verified failed/cancelled with PayPal
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    plan = models.CharField(max_length=10, choices=PLAN_CHOICES)

    # Our unique reference, generated before we ever call PayPal. Sent to
    # PayPal as the purchase unit's reference_id/custom_id, and used as the
    # single field for us to look a transaction up again by our own key.
    tx_ref = models.CharField(max_length=100, unique=True, db_index=True)

    # PayPal's own identifiers for the transaction.
    paypal_order_id = models.CharField(max_length=100, blank=True, default='', db_index=True)
    paypal_capture_id = models.CharField(max_length=100, blank=True, default='')

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    email = models.EmailField()
    phone_number = models.CharField(max_length=20, blank=True, default='')

    checkout_url = models.URLField(max_length=500, blank=True, default='')

    # Full raw JSON responses are kept for debugging/auditing. Never render
    # these directly to end users — they may contain internal PayPal fields.
    raw_create_response = models.JSONField(blank=True, null=True)
    raw_capture_response = models.JSONField(blank=True, null=True)

    failure_reason = models.CharField(max_length=255, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
        ]

    def __str__(self):
        return f'{self.tx_ref} — {self.user.username} — {self.status}'

    @property
    def is_final(self):
        """True once PayPal has given us a definitive success/failed status."""
        return self.status in ('success', 'failed')
