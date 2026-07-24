from django.contrib import admin

from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'currency', 'theme', 'email_notifications', 'created_at')
    list_filter = ('currency', 'theme', 'email_notifications')
    search_fields = ('user__username', 'user__email')
