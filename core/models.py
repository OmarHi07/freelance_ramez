from __future__ import annotations

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from core import constants
from core.i18n import LocalizedFieldsMixin
from core.validators import international_phone_validator


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        abstract = True


class SiteSettings(LocalizedFieldsMixin, models.Model):
    """Singleton row (pk=1) holding store-wide settings editable by the owner."""

    SINGLETON_PK = 1

    store_name_ar = models.CharField(_("store name (Arabic)"), max_length=120, default=constants.STORE_NAME_AR)
    store_name_en = models.CharField(_("store name (English)"), max_length=120, default=constants.STORE_NAME_EN)
    whatsapp_number = models.CharField(
        _("WhatsApp number (international)"),
        max_length=15,
        default=constants.WHATSAPP_INTERNATIONAL_NUMBER,
        validators=[international_phone_validator],
        help_text=_("Digits only with country code, used for wa.me links. Example: 972553003327"),
    )
    whatsapp_display_number = models.CharField(
        _("WhatsApp number (as displayed)"), max_length=20, default=constants.WHATSAPP_DISPLAY_NUMBER
    )
    instagram_url = models.URLField(_("Instagram URL"), default=constants.INSTAGRAM_URL)
    order_notification_email = models.EmailField(
        _("email address for new-order notifications"),
        blank=True,
        help_text=_(
            "Every new order is emailed here, with the customer's details and a WhatsApp button. "
            "Leave it empty to turn the notifications off; orders are still saved either way. "
            "This address is never shown to customers."
        ),
    )
    default_delivery_fee = models.DecimalField(
        _("default delivery fee"),
        max_digits=8,
        decimal_places=2,
        default=constants.DEFAULT_DELIVERY_FEE,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("Not used: delivery is agreed with each customer on WhatsApp after the order."),
    )
    free_delivery_threshold = models.DecimalField(
        _("free-delivery threshold"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("Orders at or above this amount (after discounts) get free delivery. Leave empty to disable."),
    )
    delivery_notice_ar = models.CharField(_("delivery notice (Arabic)"), max_length=255, blank=True)
    delivery_notice_en = models.CharField(_("delivery notice (English)"), max_length=255, blank=True)
    sale_banner_text_ar = models.CharField(_("sale banner text (Arabic)"), max_length=255, blank=True)
    sale_banner_text_en = models.CharField(_("sale banner text (English)"), max_length=255, blank=True)
    sale_banner_enabled = models.BooleanField(_("show sale banner"), default=False)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("site settings")
        verbose_name_plural = _("site settings")
        constraints = [
            models.CheckConstraint(condition=Q(pk=1), name="site_settings_singleton"),
            models.CheckConstraint(condition=Q(default_delivery_fee__gte=0), name="site_settings_fee_non_negative"),
            models.CheckConstraint(
                condition=Q(free_delivery_threshold__isnull=True) | Q(free_delivery_threshold__gte=0),
                name="site_settings_threshold_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return str(_("Site settings"))

    def save(self, *args, **kwargs):
        self.pk = self.SINGLETON_PK
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # pragma: no cover - guarded in admin as well
        raise RuntimeError("SiteSettings is a singleton and cannot be deleted.")

    @classmethod
    def load(cls) -> SiteSettings:
        obj, _created = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj

    @property
    def store_name(self) -> str:
        return self.localized("store_name")

    @property
    def delivery_notice(self) -> str:
        return self.localized("delivery_notice")

    @property
    def sale_banner_text(self) -> str:
        return self.localized("sale_banner_text")


def get_site_settings(request=None) -> SiteSettings:
    """Load settings once per request."""
    if request is not None:
        cached = getattr(request, "_rawnaq_site_settings", None)
        if cached is not None:
            return cached
    site_settings = SiteSettings.load()
    if request is not None:
        request._rawnaq_site_settings = site_settings
    return site_settings
