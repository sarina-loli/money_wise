"""Single source of truth for what each plan includes and costs.

Payments are handled by PayPal (see billing/paypal.py and billing/views.py).
Prices are charged in USD via PayPal Orders — the same figures shown on the
landing page (core/views.py) are what actually get sent to PayPal, so there's
no display-price/charged-price mismatch to worry about.
"""

# Feature limits enforced in finance/views.py. `None` means unlimited.
SAVINGS_GOAL_LIMITS = {
    'free': 1,
    'pro': None,
    'family': None,
}

EXPORT_ALLOWED_PLANS = {'pro', 'family'}

# Amount charged via PayPal for each paid plan, in USD. Adjust these to
# match your real pricing before going live — these match the display
# prices on the landing page and are suitable for sandbox test payments.
PLAN_PRICES_USD = {
    'pro': '9.00',
    'family': '19.00',
}

# Human-readable plan names, used in the PayPal checkout description and
# in Payment records.
PLAN_NAMES = {
    'pro': 'Pro',
    'family': 'Family',
}
