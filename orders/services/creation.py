"""Order creation service.

Totals are always recalculated on the server from current catalogue data and
active promotions. Nothing submitted by the browser is trusted except the
customer's own contact/address input. Stock is *not* reduced here: it is
reduced once when the owner confirms the order (see ``status.py``).

No delivery fee is added: the owner agrees it with the customer on WhatsApp
afterwards, so every new order stores ``delivery_fee = 0``. Once the order
commits, the owner is emailed (see ``notifications.py``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from cart.models import Cart, CartItem
from cart.services import cart_items_queryset
from catalog.services.pricing import price_lines
from core.models import get_site_settings
from orders.models import Order, OrderItem, OrderStatus, OrderStatusHistory
from orders.services.notifications import schedule_new_order_email
from orders.services.numbers import unique_order_number

logger = logging.getLogger("rawnaq.orders")


class CheckoutError(Exception):
    def __init__(self, code: str, products: list[str] | None = None):
        super().__init__(code)
        self.code = code
        self.products = products or []


@dataclass(frozen=True)
class DeliveryDetails:
    city: str
    street: str
    building_number: str
    apartment: str = ""
    postal_code: str = ""
    landmark: str = ""


@dataclass(frozen=True)
class SharedLocation:
    """Coordinates the customer explicitly chose to share at checkout."""

    latitude: Decimal
    longitude: Decimal
    accuracy_m: Decimal | None = None

    def normalized(self) -> SharedLocation:
        lat = Decimal(self.latitude).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        lng = Decimal(self.longitude).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        if not (Decimal(-90) <= lat <= Decimal(90) and Decimal(-180) <= lng <= Decimal(180)):
            raise CheckoutError("invalid_location")
        accuracy = None
        if self.accuracy_m is not None:
            accuracy = min(max(Decimal(self.accuracy_m), Decimal(0)), Decimal("99999999")).quantize(
                Decimal("0.1"), rounding=ROUND_HALF_UP
            )
        return SharedLocation(latitude=lat, longitude=lng, accuracy_m=accuracy)


def create_order_from_cart(
    *,
    user,
    cart: Cart,
    delivery: DeliveryDetails,
    phone: str,
    customer_notes: str = "",
    location: SharedLocation | None = None,
    language: str = "ar",
    request=None,
) -> Order:
    if not user.is_authenticated:
        raise CheckoutError("login_required")
    now = timezone.now()
    location = location.normalized() if location is not None else None

    with transaction.atomic():
        # Lock the cart so a double-submitted form cannot create two orders.
        locked = Cart.objects.select_for_update().filter(pk=cart.pk, user=user).first()
        if locked is None:
            raise CheckoutError("empty")
        items: list[CartItem] = list(cart_items_queryset(locked))
        if not items:
            raise CheckoutError("empty")

        unavailable, short = [], []
        for item in items:
            variant, product = item.variant, item.variant.product
            if not (variant.is_active and product.is_active and product.brand.is_active):
                unavailable.append(product.name)
            elif item.quantity > variant.stock_quantity:
                short.append(product.name)
        if unavailable:
            raise CheckoutError("unavailable", unavailable)
        if short:
            raise CheckoutError("insufficient_stock", short)

        totals = price_lines([(item.variant, item.quantity) for item in items], get_site_settings(request), now=now)

        order = Order(
            number=unique_order_number(lambda n: Order.objects.filter(number=n).exists(), now=now),
            customer=user,
            customer_name=user.full_name,
            customer_email=user.email,
            customer_phone=phone,
            city=delivery.city,
            street=delivery.street,
            building_number=delivery.building_number,
            apartment=delivery.apartment,
            postal_code=delivery.postal_code,
            landmark=delivery.landmark,
            subtotal=totals.subtotal,
            discount_total=totals.discount_total,
            delivery_fee=totals.delivery_fee,
            total=totals.total,
            status=OrderStatus.PENDING,
            customer_notes=(customer_notes or "").strip()[:500],
            language="en" if language.startswith("en") else "ar",
        )
        if location is not None:
            order.latitude = location.latitude
            order.longitude = location.longitude
            order.location_accuracy_m = location.accuracy_m
            order.location_consent_at = now
        order.save()

        OrderItem.objects.bulk_create(
            [
                OrderItem(
                    order=order,
                    product=line.variant.product,
                    variant=line.variant,
                    promotion=line.quote.promotion,
                    promotion_name=line.quote.promotion.name_en if line.quote.promotion else "",
                    product_name_ar=line.variant.product.name_ar,
                    product_name_en=line.variant.product.name_en,
                    variant_name_ar=line.variant.name_ar,
                    variant_name_en=line.variant.name_en,
                    brand_name=line.variant.product.brand.name_en,
                    sku=line.variant.sku,
                    quantity=line.quantity,
                    original_unit_price=line.quote.original,
                    unit_discount=line.quote.discount,
                    final_unit_price=line.quote.final,
                    line_total=line.line_total,
                )
                for line in totals.lines
            ]
        )
        OrderStatusHistory.objects.create(order=order, from_status="", to_status=OrderStatus.PENDING)
        CartItem.objects.filter(cart=locked).delete()
        # Fires only once this transaction commits, so a rolled-back checkout
        # sends nothing and the customer never waits on SMTP to see the page.
        schedule_new_order_email(order, request=request)

    logger.info("Order created", extra={"event": "order_created", "order_number": order.number})
    return order
