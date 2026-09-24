import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from catalog.models import ProductVariant
from core.models import TimeStampedModel


class Cart(TimeStampedModel):
    """Shopping cart.

    Anonymous carts are referenced from the (signed, server-side) session by
    their random UUID. Authenticated users have at most one cart.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="cart",
        verbose_name=_("customer"),
    )

    class Meta:
        verbose_name = _("cart")
        verbose_name_plural = _("carts")
        indexes = [models.Index(fields=["updated_at"], name="cart_updated_idx", condition=Q(user__isnull=True))]

    def __str__(self) -> str:
        return f"Cart {self.pk}"


class CartItem(TimeStampedModel):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items", verbose_name=_("cart"))
    variant = models.ForeignKey(
        ProductVariant, on_delete=models.CASCADE, related_name="cart_items", verbose_name=_("variant")
    )
    quantity = models.PositiveIntegerField(_("quantity"), default=1)

    class Meta:
        verbose_name = _("cart item")
        verbose_name_plural = _("cart items")
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["cart", "variant"], name="cart_unique_variant_per_cart"),
            models.CheckConstraint(condition=Q(quantity__gte=1), name="cart_item_quantity_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.variant}"
