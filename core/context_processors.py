from django.conf import settings


def site_settings(request):
    """Makes site-wide variables available in every template."""
    context = {
        'SITE_NAME': settings.SITE_NAME,
        'currency_symbol': '$',
    }
    if request.user.is_authenticated:
        from finance.models import Notification
        context['unread_count'] = Notification.objects.filter(user=request.user, is_read=False).count()
        context['currency_symbol'] = request.user.profile.currency_symbol
    return context
