from django.contrib.auth.models import User
from django.db import models


class Profile(models.Model):
    """Extra per-user settings that don't belong on Django's built-in User."""

    CURRENCY_CHOICES = [
        ('USD', 'US Dollar ($)'),
        ('EUR', 'Euro (€)'),
        ('GBP', 'British Pound (£)'),
        ('ETB', 'Ethiopian Birr (Br)'),
        ('INR', 'Indian Rupee (₹)'),
        ('NGN', 'Nigerian Naira (₦)'),
    ]

    # Maps each currency code to the symbol/prefix that should be displayed
    # everywhere a monetary amount is shown across the site.
    CURRENCY_SYMBOLS = {
        'USD': '$',
        'EUR': '€',
        'GBP': '£',
        'ETB': 'Br',
        'INR': '₹',
        'NGN': '₦',
    }

    THEME_CHOICES = [
        ('light', 'Light Mode'),
        ('dark', 'Dark Mode'),
    ]

    PLAN_CHOICES = [
        ('free', 'Free'),
        ('pro', 'Pro'),
        ('family', 'Family'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='USD')
    theme = models.CharField(max_length=5, choices=THEME_CHOICES, default='light')
    email_notifications = models.BooleanField(default=True)
    reminder_notifications = models.BooleanField(default=True)

    # --- Billing / subscription -----------------------------------------
    # No payment processor is used in this build (see billing/views.py) —
    # "starting a plan" just activates a local free trial. The two
    # stripe_* fields are kept (always blank) so the schema is ready to
    # drop a real provider back in later without another migration.
    plan = models.CharField(max_length=10, choices=PLAN_CHOICES, default='free')
    stripe_customer_id = models.CharField(max_length=255, blank=True, default='')
    stripe_subscription_id = models.CharField(max_length=255, blank=True, default='')
    # 'trialing' while a free trial is active, '' once it's ended/never started.
    subscription_status = models.CharField(max_length=20, blank=True, default='')
    current_period_end = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.username} profile'

    @property
    def currency_symbol(self):
        """Symbol/prefix to display for this user's chosen currency (e.g. Br for ETB)."""
        return self.CURRENCY_SYMBOLS.get(self.currency, '$')

    @property
    def has_active_subscription(self):
        """True while Stripe confirms the paid subscription is in good standing."""
        return self.plan != 'free' and self.subscription_status in ('active', 'trialing')

    @property
    def is_pro(self):
        return self.has_active_subscription and self.plan in ('pro', 'family')

    @property
    def is_family(self):
        return self.has_active_subscription and self.plan == 'family'
