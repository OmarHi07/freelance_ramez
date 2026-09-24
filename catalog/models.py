from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from catalog.skus import generate_product_sku, generate_variant_sku
from core import colors
from core.i18n import LocalizedFieldsMixin, localized_value
from core.images import (
    BRAND_BANNER,
    BRAND_LOGO,
    CATEGORY_IMAGE,
    PRODUCT_IMAGE,
    UploadTo,
    capped,
    crop_and_optimize,
    delete_replaced_files,
    image_dimensions,
    optimize_field_if_new,
)
from core.models import TimeStampedModel
from core.validators import IMAGE_VALIDATORS, hex_color_validator

HEX_COLOR_REGEX = r"^#[0-9A-Fa-f]{6}$"

# The single-option name used when a product has no real choice to make.
# Stored in both languages so storefront pages never fall back.
STANDARD_OPTION_NAME_AR = "قياسي"
STANDARD_OPTION_NAME_EN = "Standard"


class Brand(LocalizedFieldsMixin, TimeStampedModel):
    name_ar = models.CharField(_("name (Arabic)"), max_length=120)
    name_en = models.CharField(_("name (English)"), max_length=120)
    slug = models.SlugField(_("slug"), max_length=140, unique=True, allow_unicode=False)
    logo = models.ImageField(
        _("logo / image"), upload_to=UploadTo("brands/logos"), validators=IMAGE_VALIDATORS, blank=True
    )
    banner_image = models.ImageField(
        _("banner image"), upload_to=UploadTo("brands/banners"), validators=IMAGE_VALIDATORS, blank=True
    )
    primary_color = models.CharField(
        _("primary colour"), max_length=7, default="#F8C8DC", validators=[hex_color_validator]
    )
    secondary_color = models.CharField(
        _("secondary colour"), max_length=7, default="#9E526F", validators=[hex_color_validator]
    )
    display_order = models.PositiveIntegerField(_("display order"), default=0)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("brand")
        verbose_name_plural = _("brands")
        ordering = ["display_order", "name_en"]
        indexes = [models.Index(fields=["is_active", "display_order"], name="catalog_brand_active_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(primary_color__regex=HEX_COLOR_REGEX), name="brand_primary_color_hex"),
            models.CheckConstraint(
                condition=Q(secondary_color__regex=HEX_COLOR_REGEX), name="brand_secondary_color_hex"
            ),
        ]

    def __str__(self) -> str:
        return self.name_en or self.name_ar

    def save(self, *args, **kwargs):
        self.primary_color = colors.safe_hex(self.primary_color, colors.FALLBACK_PRIMARY)
        self.secondary_color = colors.safe_hex(self.secondary_color, colors.FALLBACK_SECONDARY)
        delete_replaced_files(self, ["logo", "banner_image"], only_uncommitted=True)
        # Square logo (shown in a circular mask) and a wide 16:5 brand-page banner.
        optimize_field_if_new(self, "logo", BRAND_LOGO)
        optimize_field_if_new(self, "banner_image", BRAND_BANNER)
        super().save(*args, **kwargs)

    @property
    def name(self) -> str:
        return self.localized("name")

    @property
    def text_on_primary(self) -> str:
        return colors.readable_text_color(self.primary_color)

    @property
    def text_on_secondary(self) -> str:
        return colors.readable_text_color(self.secondary_color)

    def get_absolute_url(self) -> str:
        return reverse("catalog:brand_detail", kwargs={"slug": self.slug})


class Category(LocalizedFieldsMixin, TimeStampedModel):
    name_ar = models.CharField(_("name (Arabic)"), max_length=120)
    name_en = models.CharField(_("name (English)"), max_length=120)
    slug = models.SlugField(_("slug"), max_length=140, unique=True)
    image = models.ImageField(_("image"), upload_to=UploadTo("categories"), validators=IMAGE_VALIDATORS, blank=True)
    display_order = models.PositiveIntegerField(_("display order"), default=0)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("category")
        verbose_name_plural = _("categories")
        ordering = ["display_order", "name_en"]
        indexes = [models.Index(fields=["is_active", "display_order"], name="catalog_category_active_idx")]

    def __str__(self) -> str:
        return self.name_en or self.name_ar

    def save(self, *args, **kwargs):
        delete_replaced_files(self, ["image"], only_uncommitted=True)
        optimize_field_if_new(self, "image", CATEGORY_IMAGE)
        super().save(*args, **kwargs)

    @property
    def name(self) -> str:
        return self.localized("name")


class VerificationStatus(models.TextChoices):
    CONFIRMED = "CONFIRMED", _("Confirmed by brand")
    NOT_CONFIRMED = "NOT_CONFIRMED", _("Not confirmed by brand")
    UNKNOWN = "UNKNOWN", _("Status unknown")


class Product(LocalizedFieldsMixin, TimeStampedModel):
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="products", verbose_name=_("brand"))
    categories = models.ManyToManyField(Category, related_name="products", blank=True, verbose_name=_("categories"))
    name_ar = models.CharField(_("name (Arabic)"), max_length=200)
    name_en = models.CharField(_("name (English)"), max_length=200)
    slug = models.SlugField(_("slug"), max_length=220, unique=True)
    description_ar = models.TextField(_("description (Arabic)"), blank=True)
    description_en = models.TextField(_("description (English)"), blank=True)
    sku = models.CharField(
        _("product code (SKU)"),
        max_length=64,
        unique=True,
        default=generate_product_sku,
        editable=False,
        help_text=_("Generated automatically. It never changes once the product exists."),
    )
    regular_price = models.DecimalField(
        _("regular price (₪)"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    verification_status = models.CharField(
        _("brand verification"),
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.UNKNOWN,
    )
    is_featured = models.BooleanField(_("featured"), default=False)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("product")
        verbose_name_plural = _("products")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["brand", "is_active"], name="catalog_product_brand_idx"),
            models.Index(fields=["is_active", "-created_at"], name="catalog_product_new_idx"),
            models.Index(fields=["is_featured", "is_active"], name="catalog_product_featured_idx"),
            models.Index(fields=["verification_status"], name="catalog_product_verif_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(regular_price__gt=0), name="product_regular_price_positive"),
        ]

    def __str__(self) -> str:
        return self.name_en or self.name_ar

    def save(self, *args, **kwargs):
        # Defence in depth: the field default covers normal creation, this
        # covers rows built with an explicitly blank SKU. Existing codes are
        # never touched, so editing a product cannot change its SKU.
        if not self.sku:
            self.sku = generate_product_sku()
        super().save(*args, **kwargs)

    @property
    def name(self) -> str:
        return self.localized("name")

    @property
    def description(self) -> str:
        return self.localized("description")

    def get_absolute_url(self) -> str:
        return reverse("catalog:product_detail", kwargs={"slug": self.slug})

    @property
    def visible_categories(self) -> list[Category]:
        return [category for category in self.categories.all() if category.is_active]

    @property
    def sorted_images(self) -> list[ProductImage]:
        """Images ordered for display, primary first (uses the prefetch cache)."""
        images = list(self.images.all())
        images.sort(key=lambda image: (not image.is_primary, image.display_order, image.pk or 0))
        return images

    @property
    def primary_image(self) -> ProductImage | None:
        images = self.sorted_images
        return images[0] if images else None

    @property
    def active_variants(self) -> list[ProductVariant]:
        return [variant for variant in self.variants.all() if variant.is_active]

    @property
    def total_stock(self) -> int:
        return sum(variant.stock_quantity for variant in self.active_variants)

    @property
    def is_in_stock(self) -> bool:
        return self.total_stock > 0

    @property
    def is_low_stock(self) -> bool:
        return 0 < self.total_stock <= settings.LOW_STOCK_THRESHOLD


class ProductVariant(LocalizedFieldsMixin, TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants", verbose_name=_("product"))
    name_ar = models.CharField(_("variant name (Arabic)"), max_length=120)
    name_en = models.CharField(_("variant name (English)"), max_length=120)
    color_name_ar = models.CharField(_("colour name (Arabic)"), max_length=60, blank=True)
    color_name_en = models.CharField(_("colour name (English)"), max_length=60, blank=True)
    color_hex = models.CharField(
        _("colour swatch"), max_length=7, blank=True, validators=[hex_color_validator], help_text=_("#RRGGBB, optional")
    )
    sku = models.CharField(
        _("option code (SKU)"),
        max_length=64,
        unique=True,
        default=generate_variant_sku,
        editable=False,
        help_text=_("Generated automatically. It never changes once the option exists."),
    )
    stock_quantity = models.PositiveIntegerField(_("stock quantity"), default=0)
    price_override = models.DecimalField(
        _("price override (₪)"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text=_("Leave empty to use the product's regular price."),
    )
    display_order = models.PositiveIntegerField(_("display order"), default=0)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("product variant")
        verbose_name_plural = _("product variants")
        ordering = ["display_order", "id"]
        indexes = [
            models.Index(fields=["product", "is_active"], name="catalog_variant_product_idx"),
            models.Index(fields=["stock_quantity"], name="catalog_variant_stock_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(stock_quantity__gte=0), name="variant_stock_non_negative"),
            models.CheckConstraint(
                condition=Q(price_override__isnull=True) | Q(price_override__gt=0),
                name="variant_price_override_positive",
            ),
            models.CheckConstraint(
                condition=Q(color_hex="") | Q(color_hex__regex=HEX_COLOR_REGEX), name="variant_color_hex_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product} — {self.name_en or self.name_ar}"

    def save(self, *args, **kwargs):
        if not self.sku:
            self.sku = generate_variant_sku()
        super().save(*args, **kwargs)

    @property
    def is_standard_option(self) -> bool:
        """True when this option carries the localized "Standard" names."""
        return self.name_ar == STANDARD_OPTION_NAME_AR and self.name_en == STANDARD_OPTION_NAME_EN

    @property
    def name(self) -> str:
        return self.localized("name")

    @property
    def color_name(self) -> str:
        return self.localized("color_name")

    @property
    def base_price(self) -> Decimal:
        return self.price_override if self.price_override is not None else self.product.regular_price

    @property
    def is_available(self) -> bool:
        return self.is_active and self.stock_quantity > 0

    @property
    def is_low_stock(self) -> bool:
        return 0 < self.stock_quantity <= settings.LOW_STOCK_THRESHOLD


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images", verbose_name=_("product"))
    image = models.ImageField(_("image"), upload_to=UploadTo("products"), validators=IMAGE_VALIDATORS)
    thumbnail = models.ImageField(_("thumbnail"), upload_to=UploadTo("products/thumbs"), blank=True, editable=False)
    alt_text_ar = models.CharField(_("alt text (Arabic)"), max_length=200, blank=True)
    alt_text_en = models.CharField(_("alt text (English)"), max_length=200, blank=True)
    display_order = models.PositiveIntegerField(_("display order"), default=0)
    is_primary = models.BooleanField(_("primary image"), default=False)
    width = models.PositiveIntegerField(null=True, blank=True, editable=False)
    height = models.PositiveIntegerField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = _("product image")
        verbose_name_plural = _("product images")
        ordering = ["-is_primary", "display_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["product"], condition=Q(is_primary=True), name="catalog_one_primary_image_per_product"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product} #{self.display_order}"

    @property
    def alt_text(self) -> str:
        return localized_value(self, "alt_text") or self.product.name

    @property
    def display_url(self) -> str:
        return self.image.url

    @property
    def thumbnail_url(self) -> str:
        return self.thumbnail.url if self.thumbnail else self.image.url

    def save(self, *args, **kwargs):
        is_new_file = bool(self.image) and not getattr(self.image, "_committed", True)
        if is_new_file:
            delete_replaced_files(self, ["image", "thumbnail"], force=True)
            source = self.image.file
            # Both are square, so a card thumbnail always matches its gallery
            # image. Replacing an image regenerates the thumbnail from the new file.
            optimized = crop_and_optimize(source, capped(PRODUCT_IMAGE, settings.IMAGE_OPTIMIZE_MAX_EDGE))
            thumb = crop_and_optimize(source, capped(PRODUCT_IMAGE, settings.IMAGE_THUMBNAIL_EDGE))
            self.width, self.height = image_dimensions(optimized) or (None, None)
            self.image.save("image.webp", optimized, save=False)
            self.thumbnail.save("thumb.webp", thumb, save=False)
        with transaction.atomic():
            if self.is_primary and self.product_id:
                ProductImage.objects.filter(product_id=self.product_id, is_primary=True).exclude(pk=self.pk).update(
                    is_primary=False
                )
            super().save(*args, **kwargs)


class DiscountType(models.TextChoices):
    PERCENTAGE = "PERCENTAGE", _("Percentage")
    FIXED = "FIXED", _("Fixed amount (₪)")


class PromotionScope(models.TextChoices):
    STORE = "STORE", _("Entire store")
    BRAND = "BRAND", _("Brand")
    CATEGORY = "CATEGORY", _("Category")
    PRODUCT = "PRODUCT", _("Individual product")


class PromotionQuerySet(models.QuerySet):
    def active(self, now=None):
        now = now or timezone.now()
        return self.filter(is_enabled=True, starts_at__lte=now).filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))


class Promotion(LocalizedFieldsMixin, TimeStampedModel):
    """A single discount rule. Only one promotion ever applies to an item (no stacking)."""

    name_ar = models.CharField(_("name (Arabic)"), max_length=150)
    name_en = models.CharField(_("name (English)"), max_length=150)
    discount_type = models.CharField(_("discount type"), max_length=12, choices=DiscountType.choices)
    value = models.DecimalField(
        _("value"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text=_("Percentage (1-100) or a fixed amount in shekels."),
    )
    scope = models.CharField(_("applies to"), max_length=10, choices=PromotionScope.choices)
    brand = models.ForeignKey(
        Brand, on_delete=models.CASCADE, null=True, blank=True, related_name="promotions", verbose_name=_("brand")
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="promotions",
        verbose_name=_("category"),
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, null=True, blank=True, related_name="promotions", verbose_name=_("product")
    )
    starts_at = models.DateTimeField(_("starts at"), default=timezone.now)
    ends_at = models.DateTimeField(_("ends at"), null=True, blank=True, help_text=_("Leave empty for no end date."))
    is_enabled = models.BooleanField(_("enabled"), default=True)
    priority = models.PositiveSmallIntegerField(
        _("priority"),
        default=0,
        help_text=_(
            "Higher priority wins when several promotions match an item. "
            "With equal priority, the biggest discount is applied."
        ),
    )

    objects = PromotionQuerySet.as_manager()

    class Meta:
        verbose_name = _("promotion")
        verbose_name_plural = _("promotions")
        ordering = ["-priority", "-starts_at"]
        indexes = [models.Index(fields=["is_enabled", "starts_at", "ends_at"], name="catalog_promo_active_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(value__gt=0), name="promotion_value_positive"),
            models.CheckConstraint(
                condition=Q(discount_type="FIXED") | Q(discount_type="PERCENTAGE", value__lte=100),
                name="promotion_percentage_max_100",
            ),
            models.CheckConstraint(
                condition=Q(ends_at__isnull=True) | Q(ends_at__gt=models.F("starts_at")),
                name="promotion_end_after_start",
            ),
            models.CheckConstraint(
                condition=(
                    Q(scope="STORE", brand__isnull=True, category__isnull=True, product__isnull=True)
                    | Q(scope="BRAND", brand__isnull=False, category__isnull=True, product__isnull=True)
                    | Q(scope="CATEGORY", brand__isnull=True, category__isnull=False, product__isnull=True)
                    | Q(scope="PRODUCT", brand__isnull=True, category__isnull=True, product__isnull=False)
                ),
                name="promotion_scope_target_consistent",
            ),
        ]

    def __str__(self) -> str:
        return self.name_en or self.name_ar

    @property
    def name(self) -> str:
        return self.localized("name")

    def is_active_at(self, when=None) -> bool:
        when = when or timezone.now()
        return self.is_enabled and self.starts_at <= when and (self.ends_at is None or self.ends_at > when)

    def clean(self):
        super().clean()
        errors: dict[str, list] = {}
        if self.value is not None:
            if self.value <= 0:
                errors.setdefault("value", []).append(_("The discount value must be greater than zero."))
            if self.discount_type == DiscountType.PERCENTAGE and self.value > 100:
                errors.setdefault("value", []).append(_("A percentage discount cannot exceed 100%."))
            if (
                self.discount_type == DiscountType.FIXED
                and self.scope == PromotionScope.PRODUCT
                and self.product_id
                and self.value > self.product.regular_price
            ):
                errors.setdefault("value", []).append(
                    _("A fixed discount cannot be larger than the product price (%(price)s).")
                    % {"price": self.product.regular_price}
                )
        if self.ends_at and self.starts_at and self.ends_at <= self.starts_at:
            errors.setdefault("ends_at", []).append(_("The end date must be after the start date."))
        targets = {
            PromotionScope.BRAND: ("brand", _("Choose the brand this promotion applies to.")),
            PromotionScope.CATEGORY: ("category", _("Choose the category this promotion applies to.")),
            PromotionScope.PRODUCT: ("product", _("Choose the product this promotion applies to.")),
        }
        required = targets.get(self.scope, (None, None))[0]
        for field, message in targets.values():
            has_value = getattr(self, f"{field}_id") is not None
            if field == required and not has_value:
                errors.setdefault(field, []).append(message)
            elif field != required and has_value:
                # Targets that do not match the chosen scope are cleared.
                setattr(self, field, None)
        if errors:
            raise ValidationError(errors)
