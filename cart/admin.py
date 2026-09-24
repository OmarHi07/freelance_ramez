from django.contrib import admin

from cart.models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    raw_id_fields = ("variant",)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "updated_at")
    list_select_related = ("user",)
    search_fields = ("user__email",)
    raw_id_fields = ("user",)
    inlines = [CartItemInline]
