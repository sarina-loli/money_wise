from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
import os
import resend

from .models import ContactMessage

def landing(request):
    """Public marketing landing page."""
    stats = [
        {'value': 25000, 'suffix': '+', 'label': 'Active Users'},
        {'value': 120, 'suffix': 'M+', 'label': 'Tracked in Transactions'},
        {'value': 98, 'suffix': '%', 'label': 'Satisfaction Rate'},
        {'value': 4.9, 'suffix': '/5', 'label': 'Average Rating'},
    ]
    features = [
        {'icon': '💳', 'title': 'Expense Tracking', 'desc': 'Log and categorize every expense in seconds with smart auto-categorization.'},
        {'icon': '📊', 'title': 'Visual Reports', 'desc': 'Beautiful, animated charts that turn raw numbers into real insight.'},
        {'icon': '🎯', 'title': 'Savings Goals', 'desc': 'Set targets and watch your progress bar fill up as you save.'},
        {'icon': '🔔', 'title': 'Smart Alerts', 'desc': 'Get notified before you overspend, not after.'},
        {'icon': '🧾', 'title': 'Budget Planning', 'desc': 'Build monthly budgets by category and track them in real time.'},
        {'icon': '🔒', 'title': 'Bank-Grade Security', 'desc': 'Your data is encrypted and protected at every layer.'},
    ]
    steps = [
        {'step': '01', 'title': 'Create your account', 'desc': 'Sign up in under a minute — no credit card required.'},
        {'step': '02', 'title': 'Connect your finances', 'desc': 'Add income, expenses, and set your first budget.'},
        {'step': '03', 'title': 'Track & grow', 'desc': 'Watch insights roll in and hit your savings goals faster.'},
    ]
    pricing = [
        {'slug': 'free', 'name': 'Free', 'price': '0', 'period': 'forever', 'features': ['Track unlimited transactions', 'Basic reports', '1 savings goal', 'Email support'], 'highlighted': False},
        {'slug': 'pro', 'name': 'Pro', 'price': '9', 'period': 'month', 'trial_note': 'First month free', 'features': ['Everything in Free', 'Advanced analytics', 'Unlimited savings goals', 'PDF/Excel export', 'Priority support'], 'highlighted': True},
        {'slug': 'family', 'name': 'Family', 'price': '19', 'period': 'month', 'trial_note': 'First month free', 'features': ['Everything in Pro', 'Up to 5 members', 'Shared budgets', 'Dedicated support'], 'highlighted': False},
    ]
    testimonials = [
        {'name': 'Amara T.', 'role': 'Freelance Designer', 'quote': 'MoneyWise is the first budgeting app I have actually stuck with for more than a month.'},
        {'name': 'Daniel K.', 'role': 'Software Engineer', 'quote': 'The savings goal tracker and alerts changed how I think about spending.'},
        {'name': 'Priya S.', 'role': 'Small Business Owner', 'quote': 'Clean, fast, and genuinely beautiful. It feels like a premium banking app.'},
    ]
    faqs = [
        {'q': 'Is MoneyWise free to use?', 'a': 'Yes, our Free plan lets you track unlimited transactions and manage one savings goal at no cost.'},
        {'q': 'Is my financial data secure?', 'a': 'All data is encrypted in transit and at rest, with industry-standard authentication and CSRF protection.'},
        {'q': 'Can I export my reports?', 'a': 'Pro and Family plans support PDF and Excel export for daily, weekly, monthly, and yearly reports.'},
        {'q': 'Can I cancel anytime?', 'a': 'Absolutely — there are no long-term contracts. Cancel or downgrade whenever you like.'},
    ]
    context = {
        'stats': stats,
        'features': features,
        'steps': steps,
        'pricing': pricing,
        'testimonials': testimonials,
        'faqs': faqs,
    }
    return render(request, 'core/landing.html', context)


@login_required
def dashboard(request):
    """Legacy URL kept for compatibility — the real dashboard now lives
    in the finance app."""
    return redirect('finance:dashboard')


def about(request):
    return render(request, 'core/about.html')

import logging

logger = logging.getLogger(__name__)


from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import redirect, render

import os
import resend

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render

from .models import ContactMessage

resend.api_key = os.environ["RESEND_API_KEY"]


def contact(request):
    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        subject = request.POST.get("subject", "")
        message = request.POST.get("message")

        # Save to database
        ContactMessage.objects.create(
            name=name,
            email=email,
            subject=subject,
            message=message,
        )

        # Send email using Resend
        resend.Emails.send({
            "from": "MoneyWise <contact@moneywise.com>",   # Replace with your verified sender
            "to": [settings.CONTACT_EMAIL],
            "subject": f"New Contact Message from {name}",
            "text": f"""
Name: {name}
Email: {email}
Subject: {subject}

Message:
{message}
""",
        })

        messages.success(
            request,
            "Your message has been sent successfully!"
        )
        return redirect("core:contact")

    return render(request, "core/contact.html")
def privacy_policy(request):
    return render(request, 'core/privacy.html')


def terms(request):
    return render(request, 'core/terms.html')


def help_center(request):
    faqs = [
        {'q': 'How do I add my first transaction?', 'a': 'From your dashboard, use the Quick Add button or go to Income/Expenses and click "Add".'},
        {'q': 'How do budgets work?', 'a': 'Set a monthly limit per category. MoneyWise tracks your spending against it and warns you at 80% and 100%.'},
        {'q': 'Can I export my data?', 'a': 'Yes — go to Reports and use "Export CSV" (opens in Excel/Sheets) or "Export PDF" (print to PDF).'},
        {'q': 'How do savings goals work?', 'a': 'Create a goal with a target amount, then use "Add Funds" any time you set money aside.'},
        {'q': 'Is my data private?', 'a': 'Yes — every record is scoped to your account only. See our Privacy Policy for details.'},
    ]
    return render(request, 'core/help_center.html', {'faqs': faqs})


def error_404(request, exception=None):
    return render(request, '404.html', status=404)
