from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import translation

from cart.models import Cart, CartItem
from conftest import make_product, make_user
from orders.models import Order, OrderStatus
from orders.services.creation import DeliveryDetails, create_order_from_cart
from orders.services.status import InsufficientStock, InvalidTransition, transition_order

pytestmark = pytest.mark.django_db


def create_order(variant_quantities, user=None):
    user = user or make_user()
    cart = Cart.objects.create(user=user)
    for variant, quantity in variant_quantities:
        CartItem.objects.create(cart=cart, variant=variant, quantity=quantity)
    return create_order_from_cart(
        user=user,
        cart=cart,
        delivery=DeliveryDetails(city="Haifa", street="Main", building_number="1"),
        phone="0501234567",
    )


def stock(variant):
    variant.refresh_from_db()
    return variant.stock_quantity


def test_stock_is_deducted_once_on_confirmation(site_settings, staff_user):
    variant = make_product(stock=5).variants.first()
    order = create_order([(variant, 2)])
    transition_order(order, OrderStatus.RECEIVED, actor=staff_user)
    assert stock(variant) == 5
    order = transition_order(order, OrderStatus.CONFIRMED, actor=staff_user)
    assert stock(variant) == 3
    assert order.stock_deducted_at is not None
    with pytest.raises(InvalidTransition):
        transition_order(order, OrderStatus.CONFIRMED, actor=staff_user)
    transition_order(order, OrderStatus.PREPARING, actor=staff_user)
    transition_order(order, OrderStatus.OUT_FOR_DELIVERY, actor=staff_user)
    transition_order(order, OrderStatus.DELIVERED, actor=staff_user)
    assert stock(variant) == 3


def test_confirmation_is_blocked_when_stock_is_insufficient(site_settings):
    variant = make_product(stock=5).variants.first()
    order = create_order([(variant, 4)])
    variant.stock_quantity = 2
    variant.save()
    with pytest.raises(InsufficientStock):
        transition_order(order, OrderStatus.CONFIRMED)
    order.refresh_from_db()
    assert order.status == OrderStatus.PENDING and order.stock_deducted_at is None
    assert stock(variant) == 2  # never negative, never partially deducted


def test_stock_is_restored_once_after_cancelling_confirmed_order(site_settings):
    first = make_product(stock=5).variants.first()
    second = make_product(stock=3).variants.first()
    order = create_order([(first, 2), (second, 3)])
    transition_order(order, OrderStatus.CONFIRMED)
    assert (stock(first), stock(second)) == (3, 0)
    order = transition_order(order, OrderStatus.CANCELLED)
    assert (stock(first), stock(second)) == (5, 3)
    assert order.stock_restored_at is not None
    with pytest.raises(InvalidTransition):
        transition_order(order, OrderStatus.CANCELLED)
    assert (stock(first), stock(second)) == (5, 3)


def test_cancelling_unconfirmed_order_does_not_touch_stock(site_settings):
    variant = make_product(stock=5).variants.first()
    order = create_order([(variant, 2)])
    order = transition_order(order, OrderStatus.CANCELLED)
    assert stock(variant) == 5
    assert order.stock_restored_at is None


@pytest.mark.parametrize(
    ("path", "target"),
    [
        ([], OrderStatus.DELIVERED),
        ([], OrderStatus.PREPARING),
        ([OrderStatus.CONFIRMED], OrderStatus.PENDING),
        ([OrderStatus.CANCELLED], OrderStatus.CONFIRMED),
        (
            [OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED],
            OrderStatus.CANCELLED,
        ),
        ([], "SHIPPED"),
    ],
)
def test_invalid_transitions_are_rejected(site_settings, path, target):
    order = create_order([(make_product(stock=10).variants.first(), 1)])
    for status in path:
        order = transition_order(order, status)
    before = order.status
    with pytest.raises(InvalidTransition):
        transition_order(order, target)
    order.refresh_from_db()
    assert order.status == before


def test_history_records_staff_user(site_settings, staff_user):
    order = create_order([(make_product().variants.first(), 1)])
    transition_order(order, OrderStatus.CONFIRMED, actor=staff_user, note="Checked by phone")
    change = order.status_history.last()
    assert (change.from_status, change.to_status, change.changed_by, change.note) == (
        OrderStatus.PENDING,
        OrderStatus.CONFIRMED,
        staff_user,
        "Checked by phone",
    )


def test_dashboard_status_form_updates_and_rejects(staff_client, site_settings):
    variant = make_product(stock=4).variants.first()
    order = create_order([(variant, 1)])
    with translation.override("en"):
        endpoint = reverse("dashboard:order_status", kwargs={"pk": order.pk})
    staff_client.post(endpoint, {"status": OrderStatus.CONFIRMED})
    order.refresh_from_db()
    assert order.status == OrderStatus.CONFIRMED and stock(variant) == 3
    staff_client.post(endpoint, {"status": OrderStatus.DELIVERED})  # not allowed from CONFIRMED
    order.refresh_from_db()
    assert order.status == OrderStatus.CONFIRMED


def test_customer_cannot_change_status(customer_client, site_settings):
    order = create_order([(make_product().variants.first(), 1)])
    with translation.override("en"):
        endpoint = reverse("dashboard:order_status", kwargs={"pk": order.pk})
    assert customer_client.post(endpoint, {"status": OrderStatus.CONFIRMED}).status_code == 403
    order.refresh_from_db()
    assert order.status == OrderStatus.PENDING


def test_order_totals_are_consistent_in_database(site_settings):
    order = create_order([(make_product(price="12.34").variants.first(), 3)])
    # The database constraint still covers the delivery term, which is now always zero.
    assert order.total == order.subtotal - order.discount_total + order.delivery_fee
    assert order.delivery_fee == Decimal("0.00")
    assert Order.objects.get(pk=order.pk).total == Decimal("37.02")


def test_purge_order_locations_clears_finished_orders(site_settings):
    from datetime import timedelta

    from django.core.management import call_command
    from django.utils import timezone

    from orders.services.creation import SharedLocation

    user = make_user()
    cart = Cart.objects.create(user=user)
    CartItem.objects.create(cart=cart, variant=make_product().variants.first(), quantity=1)
    order = create_order_from_cart(
        user=user,
        cart=cart,
        delivery=DeliveryDetails(city="Haifa", street="Main", building_number="1"),
        phone="0501234567",
        location=SharedLocation(latitude=Decimal("32.8"), longitude=Decimal("35.0")),
    )
    transition_order(order, OrderStatus.CANCELLED)
    Order.objects.filter(pk=order.pk).update(updated_at=timezone.now() - timedelta(days=40))
    call_command("purge_order_locations", "--days", "30", verbosity=0)
    order.refresh_from_db()
    assert order.latitude is None and order.location_consent_at is None
    assert order.street == "Main"
