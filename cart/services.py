"""Cart service: session/user cart lookup, item changes, safe merging and totals."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.db.models import Prefetch, Sum

from cart.models import Cart, CartItem
from catalog.models import Category, ProductImage, ProductVariant
from catalog.services.pricing import Totals, price_lines
from core.models import get_site_settings

SESSION_KEY = "cart_id"


class CartError(Exception):
    """Raised for user-facing cart problems (inactive product, not enough stock...)."""


def _parse_cart_id(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _session_cart(request) -> Cart | None:
    cart_id = _parse_cart_id(request.session.get(SESSION_KEY))
    if cart_id is None:
        request.session.pop(SESSION_KEY, None)
        return None
    cart = Cart.objects.filter(pk=cart_id, user__isnull=True).first()
    if cart is None:
        request.session.pop(SESSION_KEY, None)
    return cart


def get_cart(request, *, create: bool = False) -> Cart | None:
    """Return the current visitor's cart, optionally creating one."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        cart = Cart.objects.filter(user=user).first()
        if cart is None and create:
            cart, _created = Cart.objects.get_or_create(user=user)
        return cart

    cart = _session_cart(request)
    if cart is None and create:
        cart = Cart.objects.create()
        request.session[SESSION_KEY] = str(cart.pk)
    return cart


def cart_item_count(request) -> int:
    cached = getattr(request, "_rawnaq_cart_count", None)
    if cached is not None:
        return cached
    cart = get_cart(request)
    count = 0
    if cart is not None:
        count = cart.items.aggregate(total=Sum("quantity"))["total"] or 0
    request._rawnaq_cart_count = count
    return count


def _purchasable_variant(variant_id: int) -> ProductVariant:
    variant = (
        ProductVariant.objects.select_related("product__brand")
        .filter(pk=variant_id, is_active=True, product__is_active=True, product__brand__is_active=True)
        .first()
    )
    if variant is None:
        raise CartError("unavailable")
    return variant


def max_line_quantity(variant: ProductVariant) -> int:
    return min(settings.MAX_CART_LINE_QUANTITY, variant.stock_quantity)


def add_item(cart: Cart, variant_id: int, quantity: int) -> CartItem:
    variant = _purchasable_variant(variant_id)
    if variant.stock_quantity <= 0:
        raise CartError("out_of_stock")
    limit = max_line_quantity(variant)
    quantity = max(1, quantity)
    with transaction.atomic():
        item, created = CartItem.objects.select_for_update().get_or_create(
            cart=cart, variant=variant, defaults={"quantity": min(quantity, limit)}
        )
        if not created:
            item.quantity = max(1, min(item.quantity + quantity, limit))
            item.save(update_fields=["quantity", "updated_at"])
        Cart.objects.filter(pk=cart.pk).update(updated_at=item.updated_at)
    return item


def set_quantity(cart: Cart, item_id: int, quantity: int) -> CartItem | None:
    item = CartItem.objects.select_related("variant").filter(cart=cart, pk=item_id).first()
    if item is None:
        raise CartError("missing")
    if quantity <= 0:
        item.delete()
        return None
    limit = max_line_quantity(item.variant)
    if limit <= 0:
        raise CartError("out_of_stock")
    item.quantity = min(quantity, limit)
    item.save(update_fields=["quantity", "updated_at"])
    return item


def remove_item(cart: Cart, item_id: int) -> None:
    CartItem.objects.filter(cart=cart, pk=item_id).delete()


def merge_carts(source: Cart, target: Cart) -> None:
    """Move items from an anonymous ``source`` cart into ``target`` safely.

    Quantities are summed, then capped at the per-line maximum and the current
    stock. Inactive or sold-out items are dropped. The source cart is deleted.
    """
    if source.pk == target.pk:
        return
    with transaction.atomic():
        items = list(CartItem.objects.select_for_update().filter(cart=source).select_related("variant__product__brand"))
        existing = {item.variant_id: item for item in CartItem.objects.select_for_update().filter(cart=target)}
        for item in items:
            variant = item.variant
            if not (variant.is_active and variant.product.is_active and variant.product.brand.is_active):
                continue
            limit = max_line_quantity(variant)
            if limit <= 0:
                continue
            current = existing.get(variant.pk)
            if current is not None:
                current.quantity = min(current.quantity + item.quantity, limit)
                current.save(update_fields=["quantity", "updated_at"])
            else:
                CartItem.objects.create(cart=target, variant=variant, quantity=min(item.quantity, limit))
        source.delete()


def attach_session_cart_to_user(request, user) -> None:
    """Called after login: merge the anonymous cart into the user's cart."""
    cart_id = _parse_cart_id(request.session.pop(SESSION_KEY, None))
    if cart_id is None:
        return
    anonymous = Cart.objects.filter(pk=cart_id, user__isnull=True).first()
    if anonymous is None:
        return
    with transaction.atomic():
        user_cart = Cart.objects.select_for_update().filter(user=user).first()
        if user_cart is None:
            # Adopt the anonymous cart; the NULL-user filter guarantees it was never someone else's.
            updated = Cart.objects.filter(pk=anonymous.pk, user__isnull=True).update(user=user)
            if updated:
                return
            user_cart = Cart.objects.create(user=user)
        merge_carts(anonymous, user_cart)


def normalize_cart(cart: Cart) -> list[str]:
    """Clamp stored quantities to the per-line maximum and current stock.

    Returns the names of products whose quantity was reduced. Unavailable lines
    are kept (and flagged in the cart view) so the customer can see what changed.
    """
    adjusted = []
    for item in CartItem.objects.filter(cart=cart).select_related("variant__product"):
        limit = max_line_quantity(item.variant)
        if 0 < limit < item.quantity:
            item.quantity = limit
            item.save(update_fields=["quantity", "updated_at"])
            adjusted.append(item.variant.product.name)
    return adjusted


@dataclass
class CartView:
    cart: Cart | None
    items: list[CartItem]
    totals: Totals
    problems: list[str]

    @property
    def is_empty(self) -> bool:
        return not self.items


def cart_items_queryset(cart: Cart):
    return (
        CartItem.objects.filter(cart=cart)
        .select_related("variant__product__brand")
        .prefetch_related(
            Prefetch(
                "variant__product__images",
                queryset=ProductImage.objects.order_by("-is_primary", "display_order", "id"),
            ),
            Prefetch("variant__product__categories", queryset=Category.objects.all()),
        )
        .order_by("created_at", "id")
    )


def build_cart_view(request, cart: Cart | None = None) -> CartView:
    """Current cart with authoritative server-side totals.

    Unavailable lines are excluded from totals and reported in ``problems``.
    """
    cart = cart if cart is not None else get_cart(request)
    if cart is None:
        return CartView(cart=None, items=[], totals=price_lines([], get_site_settings(request)), problems=[])
    items = list(cart_items_queryset(cart))
    purchasable = []
    problems = []
    for item in items:
        variant = item.variant
        product = variant.product
        item.is_purchasable = (
            variant.is_active and product.is_active and product.brand.is_active and variant.stock_quantity > 0
        )
        item.exceeds_stock = item.quantity > variant.stock_quantity
        item.max_quantity = max(1, max_line_quantity(variant))
        if item.is_purchasable:
            purchasable.append((variant, item.quantity))
        else:
            problems.append(product.name)
    totals = price_lines(purchasable, get_site_settings(request))
    quotes = {line.variant.pk: line for line in totals.lines}
    for item in items:
        item.priced = quotes.get(item.variant_id)
    return CartView(cart=cart, items=items, totals=totals, problems=problems)
