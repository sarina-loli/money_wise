from django.contrib import admin

from .models import Household, HouseholdInvite, HouseholdMembership


class HouseholdMembershipInline(admin.TabularInline):
    model = HouseholdMembership
    extra = 0
    readonly_fields = ('user', 'role', 'joined_at')
    can_delete = False


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'member_count', 'created_at')
    search_fields = ('name', 'owner__username', 'owner__email')
    inlines = [HouseholdMembershipInline]


@admin.register(HouseholdInvite)
class HouseholdInviteAdmin(admin.ModelAdmin):
    list_display = ('email', 'household', 'status', 'invited_by', 'created_at', 'accepted_at')
    list_filter = ('status',)
    search_fields = ('email', 'household__name', 'invited_by__username')
    readonly_fields = ('token', 'created_at')
