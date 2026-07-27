from django.urls import path

from . import views

app_name = 'billing'

urlpatterns = [
    # Start a PayPal payment for a given plan ('pro' or 'family').
    path('checkout/<str:plan>/', views.create_checkout_session, name='checkout'),

    # RETURN_URL / CANCEL_URL — user's browser is sent back here after the
    # PayPal hosted checkout page (approved or cancelled).
    path('payment/return/', views.payment_return, name='payment_return'),

    # Webhook — PayPal's server calls this directly.
    path('webhook/paypal/', views.paypal_webhook, name='paypal_webhook'),

    # Local plan/subscription management.
    path('portal/', views.billing_portal, name='portal'),
    path('history/', views.payment_history, name='history'),
]
