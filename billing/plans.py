"""Single source of truth for what each plan includes.

Payments are not wired up in this build — "checking out" just starts a
local free trial (see billing/views.py). Nothing here talks to a payment
processor, so there are no price/API IDs to configure.
"""

# How long a started trial lasts before it needs to be renewed/managed.
TRIAL_DAYS = 30

# Feature limits enforced in finance/views.py. `None` means unlimited.
SAVINGS_GOAL_LIMITS = {
    'free': 1,
    'pro': None,
    'family': None,
}

EXPORT_ALLOWED_PLANS = {'pro', 'family'}
