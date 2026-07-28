from django.urls import path
from . import views

app_name = "billing"

urlpatterns = [
    # Existing PayPal Checkout Flow
    path(
        "checkout/<str:plan>/",
        views.create_checkout_session,
        name="checkout",
    ),

    path(
        "payment/return/",
        views.payment_return,
        name="payment_return",
    ),

    path(
        "webhook/paypal/",
        views.paypal_webhook,
        name="paypal_webhook",
    ),

    # Billing
    path(
        "portal/",
        views.billing_portal,
        name="portal",
    ),

    path(
        "history/",
        views.payment_history,
        name="history",
    ),
]