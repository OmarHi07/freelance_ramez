from __future__ import annotations

from django import forms
from django.conf import settings
from django.db.models import TextChoices
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from accounts.models import User
from catalog.models import (
    STANDARD_OPTION_NAME_AR,
    STANDARD_OPTION_NAME_EN,
    Brand,
    Category,
    Product,
    ProductImage,
    ProductVariant,
    Promotion,
    PromotionScope,
)
from core.images import (
    BRAND_BANNER,
    BRAND_LOGO,
    CATEGORY_IMAGE,
    PRODUCT_IMAGE,
    CropTarget,
    is_low_resolution,
    low_resolution_warning,
)
from core.models import SiteSettings
from core.validators import IMAGE_VALIDATORS
from orders.models import Order, OrderStatus

DATETIME_LOCAL_FORMAT = "%Y-%m-%dT%H:%M"
MAX_NEW_IMAGES = 10
ACCEPTED_IMAGE_TYPES = "image/jpeg,image/png,image/webp"


def crop_attrs(target: CropTarget, *, shape: str = "square", hint: str = "") -> dict[str, str]:
    """Data attributes that turn a file input into a cropper field.

    Every label is passed through so the modal speaks the owner's language.
    Without JavaScript the attributes are inert and the field stays an ordinary
    file input, which the server centre-crops to the same shape.
    """
    return {
        "accept": ACCEPTED_IMAGE_TYPES,
        "data-crop": target.name,
        "data-crop-ratio": f"{target.ratio_w}/{target.ratio_h}",
        "data-crop-shape": shape,
        "data-crop-width": str(target.max_width),
        "data-crop-height": str(target.max_height),
        "data-crop-title": _("Position and crop the picture"),
        "data-crop-hint": hint or _("Drag the picture to move it, then zoom until it fills the frame."),
        "data-crop-zoom": _("Zoom"),
        "data-crop-zoom-in": _("Zoom in"),
        "data-crop-zoom-out": _("Zoom out"),
        "data-crop-rotate-left": _("Rotate left"),
        "data-crop-rotate-right": _("Rotate right"),
        "data-crop-reset": _("Reset"),
        "data-crop-cancel": _("Cancel"),
        "data-crop-apply": _("Use this crop"),
        "data-crop-adjust": _("Adjust crop"),
        "data-crop-remove": _("Remove"),
        "data-crop-primary": _("Main picture"),
    }


class CropAttrsMixin:
    def __init__(self, target: CropTarget, *, shape: str = "square", hint: str = "", attrs=None):
        merged = crop_attrs(target, shape=shape, hint=hint)
        merged.update(attrs or {})
        super().__init__(merged)


class CropFileInput(CropAttrsMixin, forms.ClearableFileInput):
    """Single-file input wired to the cropper, keeping Django's clear checkbox."""


class CropReplaceInput(CropAttrsMixin, forms.FileInput):
    """Same, without a clear checkbox, for fields that must keep a file."""


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
        # Several files can be picked at once and each one is cropped on its own.
        attrs = crop_attrs(
            PRODUCT_IMAGE,
            hint=_("Square pictures look best on product cards and in the gallery."),
        )
        attrs["data-image-preview"] = ""
        kwargs.setdefault("widget", MultipleFileInput(attrs=attrs))
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


class LowResolutionWarningMixin:
    """Collects a friendly warning when an uploaded picture is small.

    The upload is still accepted — the owner is told the result may look soft,
    and the view surfaces the notes as warning messages.
    """

    crop_targets: dict[str, CropTarget] = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.image_warnings: list[str] = []

    def _check_resolution(self, field_name: str) -> None:
        upload = self.cleaned_data.get(field_name)
        target = self.crop_targets.get(field_name)
        if not upload or not target or getattr(upload, "_committed", False):
            return
        if is_low_resolution(upload, target):
            self.image_warnings.append(low_resolution_warning(target))

    def clean(self):
        cleaned = super().clean()
        for field_name in self.crop_targets:
            self._check_resolution(field_name)
        return cleaned


class BrandForm(LowResolutionWarningMixin, forms.ModelForm):
    crop_targets = {"logo": BRAND_LOGO, "banner_image": BRAND_BANNER}

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
            "logo": CropFileInput(
                BRAND_LOGO,
                shape="circle",
                hint=_("Shown as a circle on brand cards, and saved as a square picture."),
            ),
            "banner_image": CropFileInput(
                BRAND_BANNER,
                hint=_("The wide background picture at the top of this brand page."),
            ),
        }
        help_texts = {
            "logo": _("Square picture used as the round brand badge."),
            "banner_image": _("Background picture for this brand page. Brand cards use the brand colours instead."),
        }

    def clean_primary_color(self):
        return self.cleaned_data["primary_color"].upper()

    def clean_secondary_color(self):
        return self.cleaned_data["secondary_color"].upper()


class CategoryForm(LowResolutionWarningMixin, forms.ModelForm):
    crop_targets = {"image": CATEGORY_IMAGE}

    class Meta:
        model = Category
        fields = ("name_ar", "name_en", "slug", "image", "display_order", "is_active")
        widgets = {
            "name_en": forms.TextInput(attrs={"dir": "ltr"}),
            "name_ar": forms.TextInput(attrs={"dir": "rtl"}),
            "slug": forms.TextInput(attrs={"dir": "ltr", "data-slug-from": "id_name_en"}),
            "image": CropFileInput(CATEGORY_IMAGE),
        }
        help_texts = {"image": _("Square picture used wherever this category is shown.")}


class ProductForm(LowResolutionWarningMixin, forms.ModelForm):
    new_images = MultipleImageField(label=_("Add images"), required=False, validators=IMAGE_VALIDATORS)

    class Meta:
        model = Product
        fields = (
            "brand",
            "categories",
            "name_ar",
            "name_en",
            "slug",
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

    def clean(self):
        cleaned = super().clean()
        # new_images holds a list, so it needs its own low-resolution check.
        if any(is_low_resolution(upload, PRODUCT_IMAGE) for upload in cleaned.get("new_images") or []):
            self.image_warnings.append(low_resolution_warning(PRODUCT_IMAGE))
        return cleaned


class OptionMode(TextChoices):
    """How a variant's option name is decided. Not stored: it is inferred from the names."""

    STANDARD = "standard", _("Standard / قياسي")
    CUSTOM = "custom", _("Custom option / خيار مخصص")


class VariantForm(forms.ModelForm):
    """One row of the "Variants & stock" section.

    ``option_mode`` is a form-only choice — nothing is added to the database,
    because a variant is "standard" exactly when it carries the two localized
    Standard names. In standard mode the server fills both names itself, so the
    owner never types them and a forged POST cannot put anything else there.
    """

    option_mode = forms.ChoiceField(
        label=_("Option type"),
        choices=OptionMode.choices,
        initial=OptionMode.STANDARD,
        required=False,
        widget=forms.RadioSelect(attrs={"data-option-mode": ""}),
        help_text=_("Choose “Standard” when the product has only one option. The names are filled in for you."),
    )

    class Meta:
        model = ProductVariant
        fields = (
            "name_ar",
            "name_en",
            "color_name_ar",
            "color_name_en",
            "color_hex",
            "stock_quantity",
            "price_override",
            "display_order",
            "is_active",
        )
        widgets = {
            "name_en": forms.TextInput(attrs={"dir": "ltr"}),
            "name_ar": forms.TextInput(attrs={"dir": "rtl"}),
            "color_name_en": forms.TextInput(attrs={"dir": "ltr"}),
            "color_name_ar": forms.TextInput(attrs={"dir": "rtl"}),
            "color_hex": ColorInput(attrs={"placeholder": "#000000"}),
            "stock_quantity": forms.NumberInput(attrs={"min": "0", "inputmode": "numeric"}),
            "price_override": forms.NumberInput(attrs={"step": "0.01", "min": "0.01", "inputmode": "decimal"}),
            "display_order": forms.NumberInput(attrs={"min": "0", "inputmode": "numeric"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Names are validated in clean(): required in custom mode, filled in by
        # the server in standard mode.
        for name in ("name_ar", "name_en"):
            self.fields[name].required = False
        if self.instance.pk and not self.instance.is_standard_option:
            self.fields["option_mode"].initial = OptionMode.CUSTOM
        else:
            self.fields["option_mode"].initial = OptionMode.STANDARD

    def has_changed(self) -> bool:
        # A standard option needs no typing at all, so a row the formset marks
        # as mandatory (the first one on a new product) always counts as filled
        # in. Without this an untouched standard row would be silently dropped.
        if not self.empty_permitted:
            return True
        return super().has_changed()

    def clean_color_hex(self):
        return (self.cleaned_data.get("color_hex") or "").upper()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("DELETE"):
            return cleaned
        # An unknown or missing mode falls back to custom, which demands both
        # names — a forged POST can never skip validation this way.
        mode = cleaned.get("option_mode") or OptionMode.CUSTOM
        if mode == OptionMode.STANDARD:
            cleaned["name_ar"] = STANDARD_OPTION_NAME_AR
            cleaned["name_en"] = STANDARD_OPTION_NAME_EN
            self.errors.pop("name_ar", None)
            self.errors.pop("name_en", None)
        else:
            if not cleaned.get("name_ar"):
                self.add_error("name_ar", _("Enter the Arabic option name, or switch to “Standard”."))
            if not cleaned.get("name_en"):
                self.add_error("name_en", _("Enter the English option name, or switch to “Standard”."))
        return cleaned


class ProductImageForm(LowResolutionWarningMixin, forms.ModelForm):
    """An image the product already has: alt text, order, and an optional replacement.

    Leaving the file field empty keeps the stored picture exactly as it is, so
    saving the product never rewrites or re-crops images the owner did not touch.
    """

    crop_targets = {"image": PRODUCT_IMAGE}

    class Meta:
        model = ProductImage
        fields = ("image", "alt_text_ar", "alt_text_en", "display_order", "is_primary")
        widgets = {
            # FileInput, not ClearableFileInput: an image is removed with the
            # row's own delete tick, never by blanking the file field.
            "image": CropReplaceInput(
                PRODUCT_IMAGE,
                hint=_("Square pictures look best on product cards and in the gallery."),
            ),
            "alt_text_en": forms.TextInput(attrs={"dir": "ltr"}),
            "alt_text_ar": forms.TextInput(attrs={"dir": "rtl"}),
            "display_order": forms.NumberInput(attrs={"min": "0", "inputmode": "numeric"}),
        }
        labels = {"image": _("Replace picture")}
        help_texts = {"image": _("Leave empty to keep the current picture.")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["image"].required = False


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
    def _construct_form(self, i, **kwargs):
        form = super()._construct_form(i, **kwargs)
        if i == 0 and not self.instance.pk:
            # A new product must describe its first option, so this row is
            # always validated and always saved — even in standard mode, where
            # the owner may legitimately leave every field at its default.
            form.empty_permitted = False
        return form

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
        # The official business name is deliberately absent: it is fixed in
        # core.constants.BUSINESS_NAME and shown read-only on the settings page,
        # so it cannot be renamed by accident.
        fields = (
            "order_notification_email",
            "whatsapp_number",
            "whatsapp_display_number",
            "instagram_url",
            # The delivery fee and free-delivery threshold are intentionally not
            # editable: delivery is agreed per order on WhatsApp and checkout
            # never adds a fee, so exposing them could only cause confusion.
            "delivery_notice_ar",
            "delivery_notice_en",
            "sale_banner_enabled",
            "sale_banner_text_ar",
            "sale_banner_text_en",
        )
        widgets = {
            "order_notification_email": forms.EmailInput(attrs={"dir": "ltr", "autocomplete": "email"}),
            "whatsapp_number": forms.TextInput(attrs={"dir": "ltr", "inputmode": "numeric"}),
            "whatsapp_display_number": forms.TextInput(attrs={"dir": "ltr"}),
            "instagram_url": forms.URLInput(attrs={"dir": "ltr"}),
        }


def customer_queryset():
    return User.objects.filter(is_staff=False)
