from django.contrib import admin
from django.utils.html import format_html

from catalog.models import Brand, Category, Product, ProductImage, ProductVariant, Promotion


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = (
        "name_ar",
        "name_en",
        "color_name_ar",
        "color_name_en",
        "color_hex",
        "sku",
        "stock_quantity",
        "price_override",
        "display_order",
        "is_active",
    )


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0
    fields = ("preview", "image", "alt_text_ar", "alt_text_en", "display_order", "is_primary")
    readonly_fields = ("preview",)

    @admin.display(description="Preview")
    def preview(self, obj):
        if obj.pk and obj.thumbnail:
            return format_html('<img src="{}" alt="" style="height:56px;border-radius:6px">', obj.thumbnail.url)
        return "—"


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name_en", "name_ar", "slug", "primary_color", "secondary_color", "display_order", "is_active")
    list_editable = ("display_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name_en", "name_ar", "slug")
    prepopulated_fields = {"slug": ("name_en",)}


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name_en", "name_ar", "slug", "display_order", "is_active")
    list_editable = ("display_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name_en", "name_ar", "slug")
    prepopulated_fields = {"slug": ("name_en",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name_en", "brand", "sku", "regular_price", "verification_status", "is_featured", "is_active")
    list_filter = ("is_active", "is_featured", "verification_status", "brand", "categories")
    list_select_related = ("brand",)
    search_fields = ("name_en", "name_ar", "sku", "variants__sku")
    prepopulated_fields = {"slug": ("name_en",)}
    filter_horizontal = ("categories",)
    inlines = [ProductVariantInline, ProductImageInline]


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("sku", "product", "name_en", "stock_quantity", "price_override", "is_active")
    list_filter = ("is_active",)
    list_select_related = ("product",)
    search_fields = ("sku", "product__name_en", "product__name_ar")
    raw_id_fields = ("product",)


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ("name_en", "discount_type", "value", "scope", "starts_at", "ends_at", "priority", "is_enabled")
    list_filter = ("is_enabled", "scope", "discount_type")
    search_fields = ("name_en", "name_ar")
    raw_id_fields = ("product",)
