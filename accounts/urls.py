from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.MoneyWiseLoginView.as_view(), name='login'),
    path('logout/', views.MoneyWiseLogoutView.as_view(), name='logout'),

    path('password-reset/', views.MoneyWisePasswordResetView.as_view(), name='password_reset'),
    path('password-reset/done/', views.MoneyWisePasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', views.MoneyWisePasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/', views.MoneyWisePasswordResetCompleteView.as_view(), name='password_reset_complete'),

    path('profile/', views.profile, name='profile'),
    path('settings/', views.account_settings, name='settings'),
]
