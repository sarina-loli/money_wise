from django.urls import path

from . import views

app_name = 'billing'

urlpatterns = [
    path('checkout/success/', views.checkout_success, name='checkout_success'),
    path('checkout/cancel/', views.checkout_cancel, name='checkout_cancel'),
    path('checkout/<str:plan>/', views.create_checkout_session, name='checkout'),
    path('portal/', views.billing_portal, name='portal'),
]
