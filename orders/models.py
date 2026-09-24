from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from core.i18n import LocalizedFieldsMixin
from core.models import TimeStampedModel


class OrderStatus(models.TextChoices):
    PENDING = "PENDING", _("Pending")
    RECEIVED = "RECEIVED", _("Received")
    CONFIRMED = "CONFIRMED", _("Confirmed")
    PREPARING = "PREPARING", _("Preparing")
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY", _("Out for delivery")
    DELIVERED = "DELIVERED", _("Delivered")
    CANCELLED = "CANCELLED", _("Cancelled")


MONEY = {"max_digits": 10, "decimal_places": 2}


class Order(TimeStampedModel):
    """Authoritative order record.

    The customer submits everything on the website and never sends a message.
    Once the order commits, the owner is emailed and starts the WhatsApp
    conversation from that email or from the dashboard.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(_("order number"), max_length=24, unique=True, editable=False)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name=_("customer"),
    )
    # Customer snapshot
    customer_name = models.CharField(_("customer name"), max_length=150)
    customer_email = models.EmailField(_("customer email"))
    customer_phone = models.CharField(_("customer phone"), max_length=20)
    # Address snapshot
    city = models.CharField(_("city / town"), max_length=100)
    street = models.CharField(_("street"), max_length=150)
    building_number = models.CharField(_("building / house number"), max_length=20)
    apartment = models.CharField(_("apartment"), max_length=20, blank=True)
    postal_code = models.CharField(_("postal code"), max_length=12, blank=True)
    landmark = models.CharField(_("landmark or delivery notes"), max_length=255, blank=True)
    # Optional location, stored only after explicit consent
    latitude = models.DecimalField(_("latitude"), max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(_("longitude"), max_digits=9, decimal_places=6, null=True, blank=True)
    location_accuracy_m = models.DecimalField(
        _("location accuracy (m)"), max_digits=9, decimal_places=1, null=True, blank=True
    )
    location_consent_at = models.DateTimeField(_("location consent given at"), null=True, blank=True)
    # Totals (server-calculated)
    subtotal = models.DecimalField(_("subtotal"), **MONEY)
    discount_total = models.DecimalField(_("discount total"), **MONEY)
    delivery_fee = models.DecimalField(_("delivery fee"), **MONEY)
    total = models.DecimalField(_("total"), **MONEY)
    status = models.CharField(
        _("status"), max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING, db_index=True
    )
    customer_notes = models.TextField(_("customer notes"), blank=True, max_length=500)
    internal_notes = models.TextField(_("internal notes"), blank=True)
    language = models.CharField(_("language"), max_length=5, default="ar")
    # Legacy: the customer used to open WhatsApp themselves. Kept so historical
    # orders do not lose data; it plays no part in the current flow.
    whatsapp_opened_at = models.DateTimeField(_("WhatsApp opened at (legacy)"), null=True, blank=True, editable=False)
    owner_notification_attempted_at = models.DateTimeField(
        _("owner notified: last attempt"), null=True, blank=True, editable=False
    )
    owner_notification_sent_at = models.DateTimeField(_("owner notified: sent"), null=True, blank=True, editable=False)
    stock_deducted_at = models.DateTimeField(_("stock deducted at"), null=True, blank=True, editable=False)
    stock_restored_at = models.DateTimeField(_("stock restored at"), null=True, blank=True, editable=False)

    class Meta:
        verbose_name = _("order")
        verbose_name_plural = _("orders")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="orders_status_created_idx"),
            models.Index(fields=["customer", "-created_at"], name="orders_customer_created_idx"),
            models.Index(fields=["-created_at"], name="orders_created_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(subtotal__gte=0, discount_total__gte=0, delivery_fee__gte=0, total__gte=0),
                name="order_amounts_non_negative",
            ),
            models.CheckConstraint(condition=Q(discount_total__lte=F("subtotal")), name="order_discount_lte_subtotal"),
            models.CheckConstraint(
                condition=Q(total=F("subtotal") - F("discount_total") + F("delivery_fee")),
                name="order_total_consistent",
            ),
            models.CheckConstraint(
                condition=(
                    Q(latitude__isnull=True, longitude__isnull=True, location_consent_at__isnull=True)
                    | Q(latitude__isnull=False, longitude__isnull=False, location_consent_at__isnull=False)
                ),
                name="order_location_requires_consent",
            ),
            models.CheckConstraint(
                condition=Q(latitude__isnull=True) | Q(latitude__gte=-90, latitude__lte=90),
                name="order_latitude_range",
            ),
            models.CheckConstraint(
                condition=Q(longitude__isnull=True) | Q(longitude__gte=-180, longitude__lte=180),
                name="order_longitude_range",
            ),
            models.CheckConstraint(
                condition=Q(stock_restored_at__isnull=True) | Q(stock_deducted_at__isnull=False),
                name="order_restore_requires_deduction",
            ),
        ]

    def __str__(self) -> str:
        return self.number

    def get_absolute_url(self) -> str:
        return reverse("orders:detail", kwargs={"pk": self.pk})

    def get_owner_url(self) -> str:
        return reverse("dashboard:order_detail", kwargs={"pk": self.pk})

    @property
    def has_location(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def google_maps_url(self) -> str:
        if not self.has_location:
            return ""
        return f"https://www.google.com/maps/search/?api=1&query={self.latitude},{self.longitude}"

    @property
    def address_one_line(self) -> str:
        parts = [f"{self.street} {self.building_number}".strip()]
        if self.apartment:
            parts.append(str(_("Apt. %(apartment)s") % {"apartment": self.apartment}))
        parts.append(self.city)
        if self.postal_code:
            parts.append(self.postal_code)
        return ", ".join(part for part in parts if part)

    @property
    def items_total(self):
        return self.subtotal - self.discount_total

    @property
    def is_open(self) -> bool:
        return self.status not in (OrderStatus.DELIVERED, OrderStatus.CANCELLED)

    @property
    def owner_notification_failed(self) -> bool:
        """An attempt was made but no message left the server."""
        if self.owner_notification_attempted_at is None:
            return False
        return self.owner_notification_sent_at is None


class OrderItem(LocalizedFieldsMixin, models.Model):
    """Line item with price snapshots so later catalogue edits never change history."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items", verbose_name=_("order"))
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name=_("product")
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
        verbose_name=_("variant"),
    )
    promotion = models.ForeignKey(
        "catalog.Promotion", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    product_name_ar = models.CharField(_("product name (Arabic)"), max_length=200)
    product_name_en = models.CharField(_("product name (English)"), max_length=200)
    variant_name_ar = models.CharField(_("variant (Arabic)"), max_length=120, blank=True)
    variant_name_en = models.CharField(_("variant (English)"), max_length=120, blank=True)
    brand_name = models.CharField(_("brand"), max_length=120, blank=True)
    promotion_name = models.CharField(_("promotion"), max_length=150, blank=True)
    sku = models.CharField(_("SKU"), max_length=64)
    quantity = models.PositiveIntegerField(_("quantity"))
    original_unit_price = models.DecimalField(_("original unit price"), **MONEY)
    unit_discount = models.DecimalField(_("discount per unit"), **MONEY)
    final_unit_price = models.DecimalField(_("final unit price"), **MONEY)
    line_total = models.DecimalField(_("line total"), **MONEY)

    class Meta:
        verbose_name = _("order item")
        verbose_name_plural = _("order items")
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gte=1), name="order_item_quantity_positive"),
            models.CheckConstraint(
                condition=Q(original_unit_price__gte=0, unit_discount__gte=0, final_unit_price__gte=0),
                name="order_item_prices_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(final_unit_price=F("original_unit_price") - F("unit_discount")),
                name="order_item_final_price_consistent",
            ),
            models.CheckConstraint(
                condition=Q(line_total=F("final_unit_price") * F("quantity")),
                name="order_item_line_total_consistent",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.product_name_en}"

    @property
    def product_name(self) -> str:
        return self.localized("product_name")

    @property
    def variant_name(self) -> str:
        return self.localized("variant_name")


class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="status_history", verbose_name=_("order"))
    from_status = models.CharField(_("from"), max_length=20, choices=OrderStatus.choices, blank=True)
    to_status = models.CharField(_("to"), max_length=20, choices=OrderStatus.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("changed by"),
    )
    note = models.CharField(_("note"), max_length=255, blank=True)
    created_at = models.DateTimeField(_("changed at"), auto_now_add=True)

    class Meta:
        verbose_name = _("status change")
        verbose_name_plural = _("status history")
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["order", "created_at"], name="orders_history_order_idx")]

    def __str__(self) -> str:
        return f"{self.order_id}: {self.from_status or '—'} → {self.to_status}"
