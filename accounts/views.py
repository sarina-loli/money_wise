from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from .forms import (
    LoginForm,
    MoneyWisePasswordResetForm,
    ProfileUpdateForm,
    RegisterForm,
    SettingsForm,
)


def register(request):
    if request.user.is_authenticated:
        return redirect('finance:dashboard')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome to MoneyWise, {user.first_name}! Your account is ready.')
            return redirect('finance:dashboard')
    else:
        form = RegisterForm()

    return render(request, 'accounts/register.html', {'form': form})


class MoneyWiseLoginView(LoginView):
    template_name = 'accounts/login.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        if not form.cleaned_data.get('remember_me'):
            self.request.session.set_expiry(0)
        messages.success(self.request, 'Welcome back!')
        return response


class MoneyWiseLogoutView(LogoutView):
    next_page = 'core:landing'


class MoneyWisePasswordResetView(PasswordResetView):
    template_name = 'accounts/forgot_password.html'
    email_template_name = 'accounts/emails/password_reset_email.html'
    subject_template_name = 'accounts/emails/password_reset_subject.txt'
    form_class = MoneyWisePasswordResetForm
    success_url = reverse_lazy('accounts:password_reset_done')


class MoneyWisePasswordResetDoneView(PasswordResetDoneView):
    template_name = 'accounts/password_reset_done.html'


class MoneyWisePasswordResetConfirmView(PasswordResetConfirmView):
    template_name = 'accounts/password_reset_confirm.html'
    success_url = reverse_lazy('accounts:password_reset_complete')


class MoneyWisePasswordResetCompleteView(PasswordResetCompleteView):
    template_name = 'accounts/password_reset_complete.html'


@login_required
def profile(request):
    prof = request.user.profile
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=prof, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated.')
            return redirect('accounts:profile')
    else:
        form = ProfileUpdateForm(instance=prof, user=request.user)
    return render(request, 'accounts/profile.html', {'form': form})


@login_required
def account_settings(request):
    prof = request.user.profile
    if request.method == 'POST':
        form = SettingsForm(request.POST, instance=prof)
        if form.is_valid():
            form.save()
            messages.success(request, 'Settings saved.')
            return redirect('accounts:settings')
    else:
        form = SettingsForm(instance=prof)
    return render(request, 'accounts/settings.html', {'form': form})
