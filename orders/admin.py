from django.contrib import admin

from orders.models import Order, OrderItem, OrderStatusHistory


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = [field.name for field in OrderItem._meta.fields if field.name != "id"]

    def has_add_permission(self, request, obj=None):
        return False


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    can_delete = False
    readonly_fields = ("from_status", "to_status", "changed_by", "note", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Technical fallback. Use the owner dashboard for status changes so stock stays consistent."""

    list_display = ("number", "customer_name", "status", "total", "created_at", "whatsapp_opened_at")
    list_filter = ("status", "created_at")
    search_fields = ("number", "customer_name", "customer_email", "customer_phone")
    date_hierarchy = "created_at"
    readonly_fields = [field.name for field in Order._meta.fields if field.name not in ("internal_notes",)]
    inlines = [OrderItemInline, OrderStatusHistoryInline]

    def has_add_permission(self, request):
        return False
