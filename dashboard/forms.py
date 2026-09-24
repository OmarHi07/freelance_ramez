from __future__ import annotations

from django import forms
from django.conf import settings
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from accounts.models import User
from catalog.models import Brand, Category, Product, ProductImage, ProductVariant, Promotion, PromotionScope
from core.models import SiteSettings
from core.validators import IMAGE_VALIDATORS
from orders.models import Order, OrderStatus

DATETIME_LOCAL_FORMAT = "%Y-%m-%dT%H:%M"
MAX_NEW_IMAGES = 10


class ColorInput(forms.TextInput):
    """Text input for #RRGGBB paired with a native colour picker by dashboard.js."""

    def __init__(self, attrs=None):
        base = {
            "pattern": "#[0-9A-Fa-f]{6}",
            "maxlength": "7",
            "data-color-input": "",
            "dir": "ltr",
            "placeholder": "#F8C8DC",
        }
        base.update(attrs or {})
        super().__init__(base)


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault(
            "widget", MultipleFileInput(attrs={"accept": "image/jpeg,image/png,image/webp", "data-image-preview": ""})
        )
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            if len(data) > MAX_NEW_IMAGES:
                raise forms.ValidationError(
                    _("You can upload up to %(count)s images at a time.") % {"count": MAX_NEW_IMAGES}
                )
            return [single(item, initial) for item in data if item]
        return [single(data, initial)] if data else []


class BrandForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = (
            "name_ar",
            "name_en",
            "slug",
            "logo",
            "banner_image",
            "primary_color",
            "secondary_color",
            "display_order",
            "is_active",
        )
        widgets = {
            "primary_color": ColorInput(),
            "secondary_color": ColorInput(),
            "name_en": forms.TextInput(attrs={"dir": "ltr"}),
            "name_ar": forms.TextInput(attrs={"dir": "rtl"}),
            "slug": forms.TextInput(attrs={"dir": "ltr", "data-slug-from": "id_name_en"}),
            "logo": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
            "banner_image": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
        }

    def clean_primary_color(self):
        return self.cleaned_data["primary_color"].upper()

    def clean_secondary_color(self):
        return self.cleaned_data["secondary_color"].upper()


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ("name_ar", "name_en", "slug", "image", "display_order", "is_active")
        widgets = {
            "name_en": forms.TextInput(attrs={"dir": "ltr"}),
            "name_ar": forms.TextInput(attrs={"dir": "rtl"}),
            "slug": forms.TextInput(attrs={"dir": "ltr", "data-slug-from": "id_name_en"}),
            "image": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
        }


class ProductForm(forms.ModelForm):
    new_images = MultipleImageField(label=_("Add images"), required=False, validators=IMAGE_VALIDATORS)

    class Meta:
        model = Product
        fields = (
            "brand",
            "categories",
            "name_ar",
            "name_en",
            "slug",
            "sku",
            "description_ar",
            "description_en",
            "regular_price",
            "verification_status",
            "is_featured",
            "is_active",
        )
        widgets = {
            "categories": forms.CheckboxSelectMultiple,
            "name_en": forms.TextInput(attrs={"dir": "ltr"}),
            "name_ar": forms.TextInput(attrs={"dir": "rtl"}),
            "slug": forms.TextInput(attrs={"dir": "ltr", "data-slug-from": "id_name_en"}),
            "sku": forms.TextInput(attrs={"dir": "ltr"}),
            "description_en": forms.Textarea(attrs={"rows": 4, "dir": "ltr"}),
            "description_ar": forms.Textarea(attrs={"rows": 4, "dir": "rtl"}),
            "regular_price": forms.NumberInput(attrs={"step": "0.01", "min": "0.01", "inputmode": "decimal"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["brand"].queryset = Brand.objects.order_by("display_order", "name_en")
        self.fields["categories"].queryset = Category.objects.order_by("display_order", "name_en")
        # Built per request so the text follows the active language.
        self.fields["new_images"].help_text = _(
            "JPEG, PNG or WebP, up to %(size)s MB each. You can select several files."
        ) % {"size": settings.MAX_IMAGE_UPLOAD_SIZE // (1024 * 1024)}


class VariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
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
        widgets = {
            "color_hex": ColorInput(attrs={"placeholder": "#000000"}),
            "sku": forms.TextInput(attrs={"dir": "ltr"}),
            "stock_quantity": forms.NumberInput(attrs={"min": "0", "inputmode": "numeric"}),
            "price_override": forms.NumberInput(attrs={"step": "0.01", "min": "0.01", "inputmode": "decimal"}),
            "display_order": forms.NumberInput(attrs={"min": "0", "inputmode": "numeric"}),
        }

    def clean_color_hex(self):
        return (self.cleaned_data.get("color_hex") or "").upper()


class ProductImageForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ("alt_text_ar", "alt_text_en", "display_order", "is_primary")
        widgets = {"display_order": forms.NumberInput(attrs={"min": "0", "inputmode": "numeric"})}


class BaseImageFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        primaries = sum(
            1
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE") and form.cleaned_data.get("is_primary")
        )
        if primaries > 1:
            raise forms.ValidationError(_("Choose only one primary image."))


class BaseVariantFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        active = [
            form
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE") and form.cleaned_data.get("is_active")
        ]
        if not active:
            raise forms.ValidationError(_("A product needs at least one active variant (for example “Standard”)."))


VariantFormSet = inlineformset_factory(
    Product, ProductVariant, form=VariantForm, formset=BaseVariantFormSet, extra=1, can_delete=True
)
ImageFormSet = inlineformset_factory(
    Product, ProductImage, form=ProductImageForm, formset=BaseImageFormSet, extra=0, can_delete=True
)


class PromotionForm(forms.ModelForm):
    class Meta:
        model = Promotion
        fields = (
            "name_ar",
            "name_en",
            "discount_type",
            "value",
            "scope",
            "brand",
            "category",
            "product",
            "starts_at",
            "ends_at",
            "priority",
            "is_enabled",
        )
        widgets = {
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format=DATETIME_LOCAL_FORMAT),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format=DATETIME_LOCAL_FORMAT),
            "value": forms.NumberInput(attrs={"step": "0.01", "min": "0.01", "inputmode": "decimal"}),
            "scope": forms.Select(attrs={"data-promotion-scope": ""}),
            "name_en": forms.TextInput(attrs={"dir": "ltr"}),
            "name_ar": forms.TextInput(attrs={"dir": "rtl"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("starts_at", "ends_at"):
            self.fields[name].input_formats = [DATETIME_LOCAL_FORMAT, "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"]
        self.fields["product"].queryset = Product.objects.select_related("brand").order_by("name_en")
        for name, scope in (
            ("brand", PromotionScope.BRAND),
            ("category", PromotionScope.CATEGORY),
            ("product", PromotionScope.PRODUCT),
        ):
            self.fields[name].widget.attrs["data-scope-target"] = scope


class OrderFilterForm(forms.Form):
    q = forms.CharField(
        label=_("Search"),
        required=False,
        widget=forms.SearchInput(attrs={"placeholder": _("Order number, name, phone or email")}),
    )
    status = forms.ChoiceField(
        label=_("Status"), required=False, choices=[("", _("All statuses")), *OrderStatus.choices]
    )
    date_from = forms.DateField(label=_("From"), required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(label=_("To"), required=False, widget=forms.DateInput(attrs={"type": "date"}))


class OrderStatusForm(forms.Form):
    status = forms.ChoiceField(label=_("New status"))
    note = forms.CharField(label=_("Note (optional)"), max_length=255, required=False)

    def __init__(self, *args, order: Order, **kwargs):
        super().__init__(*args, **kwargs)
        from orders.services.status import allowed_next_statuses

        labels = dict(OrderStatus.choices)
        self.fields["status"].choices = [(value, labels[value]) for value in allowed_next_statuses(order)]


class OrderNotesForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ("internal_notes",)
        widgets = {"internal_notes": forms.Textarea(attrs={"rows": 4})}


class ProductFilterForm(forms.Form):
    q = forms.CharField(
        label=_("Search"), required=False, widget=forms.SearchInput(attrs={"placeholder": _("Name or SKU")})
    )
    brand = forms.ModelChoiceField(
        label=_("Brand"), queryset=Brand.objects.order_by("name_en"), required=False, empty_label=_("All brands")
    )
    state = forms.ChoiceField(
        label=_("Status"),
        required=False,
        choices=[("", _("All")), ("active", _("Active")), ("inactive", _("Hidden")), ("low", _("Low stock"))],
    )


class CustomerFilterForm(forms.Form):
    q = forms.CharField(
        label=_("Search"), required=False, widget=forms.SearchInput(attrs={"placeholder": _("Name, email or phone")})
    )


class StockUpdateForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ("stock_quantity",)
        widgets = {"stock_quantity": forms.NumberInput(attrs={"min": "0", "inputmode": "numeric"})}


class SiteSettingsForm(forms.ModelForm):
    instagram_url = forms.URLField(
        label=_("Instagram URL"), assume_scheme="https", widget=forms.URLInput(attrs={"dir": "ltr"})
    )

    class Meta:
        model = SiteSettings
        fields = (
            "store_name_ar",
            "store_name_en",
            "whatsapp_number",
            "whatsapp_display_number",
            "instagram_url",
            "default_delivery_fee",
            "free_delivery_threshold",
            "delivery_notice_ar",
            "delivery_notice_en",
            "sale_banner_enabled",
            "sale_banner_text_ar",
            "sale_banner_text_en",
        )
        widgets = {
            "whatsapp_number": forms.TextInput(attrs={"dir": "ltr", "inputmode": "numeric"}),
            "whatsapp_display_number": forms.TextInput(attrs={"dir": "ltr"}),
            "instagram_url": forms.URLInput(attrs={"dir": "ltr"}),
        }


def customer_queryset():
    return User.objects.filter(is_staff=False)
