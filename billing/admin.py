from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('tx_ref', 'user', 'plan', 'amount', 'currency', 'status', 'created_at', 'verified_at')
    list_filter = ('status', 'plan', 'currency')
    search_fields = ('tx_ref', 'paypal_order_id', 'paypal_capture_id', 'user__username', 'user__email', 'email')
    readonly_fields = (
        'user', 'plan', 'tx_ref', 'paypal_order_id', 'paypal_capture_id', 'amount', 'currency', 'status',
        'email', 'phone_number', 'checkout_url', 'raw_create_response',
        'raw_capture_response', 'failure_reason', 'created_at', 'updated_at', 'verified_at',
    )
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        # Payments are only ever created through the checkout flow.
        return False
