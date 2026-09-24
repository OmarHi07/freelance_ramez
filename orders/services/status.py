"""Order status transitions and stock accounting.

* Stock is reduced exactly once, when an order becomes CONFIRMED.
* Stock is restored exactly once, when a confirmed order is CANCELLED.
* Both operations lock the order row and the affected variant rows
  (``SELECT ... FOR UPDATE``, in primary-key order to avoid deadlocks) and are
  guarded by ``stock_deducted_at`` / ``stock_restored_at`` so repeating a
  request can never apply them twice. Stock can never become negative: the
  service checks first and a database CHECK constraint enforces it.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from catalog.models import ProductVariant
from orders.models import Order, OrderItem, OrderStatus, OrderStatusHistory

logger = logging.getLogger("rawnaq.orders")

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    OrderStatus.PENDING: {OrderStatus.RECEIVED, OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.RECEIVED: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.PREPARING, OrderStatus.CANCELLED},
    OrderStatus.PREPARING: {OrderStatus.OUT_FOR_DELIVERY, OrderStatus.CANCELLED},
    OrderStatus.OUT_FOR_DELIVERY: {OrderStatus.DELIVERED, OrderStatus.CANCELLED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}

# Order in which statuses are shown to customers as a progress tracker.
PROGRESS_STEPS = [
    OrderStatus.PENDING,
    OrderStatus.RECEIVED,
    OrderStatus.CONFIRMED,
    OrderStatus.PREPARING,
    OrderStatus.OUT_FOR_DELIVERY,
    OrderStatus.DELIVERED,
]


class InvalidTransition(Exception):
    def __init__(self, current: str, requested: str):
        super().__init__(f"Cannot change order status from {current} to {requested}.")
        self.current = current
        self.requested = requested


class InsufficientStock(Exception):
    def __init__(self, skus: list[str]):
        super().__init__("Not enough stock for: " + ", ".join(skus))
        self.skus = skus


def allowed_next_statuses(order: Order) -> list[str]:
    allowed = ALLOWED_TRANSITIONS.get(order.status, set())
    return [value for value, _label in OrderStatus.choices if value in allowed]


def can_transition(current: str, requested: str) -> bool:
    return requested in ALLOWED_TRANSITIONS.get(current, set())


def _quantities_by_variant(order: Order) -> dict[int, int]:
    quantities: dict[int, int] = defaultdict(int)
    for variant_id, quantity in OrderItem.objects.filter(order=order, variant__isnull=False).values_list(
        "variant_id", "quantity"
    ):
        quantities[variant_id] += quantity
    return dict(quantities)


def _deduct_stock(order: Order) -> None:
    quantities = _quantities_by_variant(order)
    variants = list(ProductVariant.objects.select_for_update().filter(pk__in=quantities).order_by("pk"))
    shortages = [variant.sku for variant in variants if variant.stock_quantity < quantities[variant.pk]]
    if shortages:
        raise InsufficientStock(shortages)
    for variant in variants:
        ProductVariant.objects.filter(pk=variant.pk).update(
            stock_quantity=F("stock_quantity") - quantities[variant.pk], updated_at=timezone.now()
        )


def _restore_stock(order: Order) -> None:
    quantities = _quantities_by_variant(order)
    variants = list(ProductVariant.objects.select_for_update().filter(pk__in=quantities).order_by("pk"))
    for variant in variants:
        ProductVariant.objects.filter(pk=variant.pk).update(
            stock_quantity=F("stock_quantity") + quantities[variant.pk], updated_at=timezone.now()
        )


def transition_order(order: Order, new_status: str, *, actor=None, note: str = "") -> Order:
    """Move ``order`` to ``new_status`` or raise ``InvalidTransition``/``InsufficientStock``."""
    if new_status not in OrderStatus.values:
        raise InvalidTransition(order.status, new_status)
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        current = locked.status
        if not can_transition(current, new_status):
            raise InvalidTransition(current, new_status)
        now = timezone.now()
        if new_status == OrderStatus.CONFIRMED and locked.stock_deducted_at is None:
            _deduct_stock(locked)
            locked.stock_deducted_at = now
        if (
            new_status == OrderStatus.CANCELLED
            and locked.stock_deducted_at is not None
            and locked.stock_restored_at is None
        ):
            _restore_stock(locked)
            locked.stock_restored_at = now
        locked.status = new_status
        locked.save(update_fields=["status", "stock_deducted_at", "stock_restored_at", "updated_at"])
        OrderStatusHistory.objects.create(
            order=locked,
            from_status=current,
            to_status=new_status,
            changed_by=actor if actor is not None and actor.is_authenticated else None,
            note=(note or "")[:255],
        )
    logger.info(
        "Order status changed",
        extra={"event": "order_status_changed", "order_number": locked.number},
    )
    return locked
