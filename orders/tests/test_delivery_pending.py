"""Checkout charges nothing for delivery, and never calls that "free"."""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import translation

from cart.models import Cart, CartItem
from conftest import make_product, make_promotion
from orders.models import Order

pytestmark = pytest.mark.django_db

ADDRESS = {"city": "Haifa", "street": "HaGefen", "building_number": "12", "phone": "050-123 4567"}
# Anything that would tell a customer delivery costs nothing.
FREE_DELIVERY_WORDS = ["Free delivery", "Free shipping", ">Free<", "توصيل مجاني", "مجاناً", "شحن مجاني"]


def url(name, lang="en", **kwargs):
    with translation.override(lang):
        return reverse(name, kwargs=kwargs or None)


def fill_cart(user, variant, quantity=1):
    cart, _ = Cart.objects.get_or_create(user=user)
    CartItem.objects.create(cart=cart, variant=variant, quantity=quantity)
    return cart


def place(client, customer, **kwargs):
    fill_cart(customer, make_product(**kwargs).variants.first())
    client.post(url("orders:checkout"), ADDRESS)
    return Order.objects.latest("created_at")


def assert_not_called_free(html, where):
    for phrase in FREE_DELIVERY_WORDS:
        assert phrase not in html, f"{where} calls delivery free ({phrase!r})"


# ---------------------------------------------------------------------------
# New orders
# ---------------------------------------------------------------------------
def test_new_orders_always_store_a_zero_delivery_fee(customer_client, customer, site_settings):
    order = place(customer_client, customer, price="75.00")
    assert order.delivery_fee == Decimal("0.00")


def test_new_order_total_is_subtotal_minus_discounts(customer_client, customer, site_settings):
    make_promotion(value="10.00")  # 10% off the store
    fill_cart(customer, make_product(price="80.00").variants.first(), quantity=2)
    customer_client.post(url("orders:checkout"), ADDRESS)
    order = Order.objects.get()

    assert order.subtotal == Decimal("160.00")
    assert order.discount_total == Decimal("16.00")
    assert order.total == order.subtotal - order.discount_total == Decimal("144.00")
    assert order.delivery_fee == Decimal("0.00")
    assert order.items_total == order.total


def test_a_stale_stored_delivery_fee_cannot_come_back(customer_client, customer, site_settings):
    """Even if an old row still holds a fee, checkout must not charge it."""
    site_settings.default_delivery_fee = Decimal("20.00")
    site_settings.free_delivery_threshold = Decimal("999.00")
    site_settings.save()

    order = place(customer_client, customer, price="50.00")
    assert order.delivery_fee == Decimal("0.00")
    assert order.total == Decimal("50.00")


# ---------------------------------------------------------------------------
# Wording
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("lang", ["en", "ar"])
def test_customer_pages_say_products_total_and_never_free(customer_client, customer, site_settings, lang):
    variant = make_product(price="50.00").variants.first()
    fill_cart(customer, variant)

    for name in ("cart:detail", "orders:checkout"):
        html = customer_client.get(url(name, lang=lang)).content.decode()
        assert_not_called_free(html, name)
        assert "₪50.00" in html
        if lang == "en":
            assert "Products total" in html
            assert "Delivery is not included in this total" in html
        else:
            assert "مجموع المنتجات" in html
            assert "رسوم التوصيل غير مشمولة" in html

    customer_client.post(url("orders:checkout"), ADDRESS)
    order = Order.objects.latest("created_at")
    for name in ("orders:confirmation", "orders:detail"):
        html = customer_client.get(url(name, lang=lang, pk=order.pk)).content.decode()
        assert_not_called_free(html, name)


def test_owner_pages_say_products_total_and_never_free(staff_client, customer, site_settings):
    fill_cart(customer, make_product(price="50.00").variants.first())
    from django.test import Client

    shopper = Client()
    shopper.force_login(customer)
    shopper.post(url("orders:checkout"), ADDRESS)
    order = Order.objects.latest("created_at")

    for target in (url("dashboard:order_list"), url("dashboard:order_detail", pk=order.pk)):
        html = staff_client.get(target).content.decode()
        assert_not_called_free(html, target)
        assert "Products total" in html


# ---------------------------------------------------------------------------
# History is never rewritten
# ---------------------------------------------------------------------------
@pytest.fixture
def historical_order(customer, site_settings):
    """An order from when delivery was still charged."""
    order = Order.objects.create(
        customer=customer,
        number="RNQ-20250101-OLD1",
        customer_name=customer.full_name,
        customer_email=customer.email,
        customer_phone="0501234567",
        city="Haifa",
        street="HaGefen",
        building_number="12",
        subtotal=Decimal("100.00"),
        discount_total=Decimal("10.00"),
        delivery_fee=Decimal("20.00"),
        total=Decimal("110.00"),
        language="en",
    )
    return order


def test_historical_orders_keep_their_delivery_fee_and_total(historical_order):
    stored = Order.objects.get(pk=historical_order.pk)
    assert stored.delivery_fee == Decimal("20.00")
    assert stored.total == Decimal("110.00")
    assert stored.items_total == Decimal("90.00")
    # The database constraint still holds for the historical shape.
    assert stored.total == stored.subtotal - stored.discount_total + stored.delivery_fee


def test_a_historical_delivery_fee_is_still_shown_to_the_customer(customer_client, historical_order):
    html = customer_client.get(url("orders:detail", pk=historical_order.pk)).content.decode()
    assert "₪20.00" in html  # the fee that was actually charged
    assert "₪110.00" in html  # the total that was actually paid
    assert "₪90.00" in html  # products total
    assert_not_called_free(html, "historical order detail")


def test_a_historical_delivery_fee_is_still_shown_to_the_owner(staff_client, historical_order):
    html = staff_client.get(url("dashboard:order_detail", pk=historical_order.pk)).content.decode()
    assert "₪20.00" in html and "₪110.00" in html
    assert "Delivery (charged at the time)" in html


def test_site_settings_no_longer_expose_delivery_controls(staff_client, site_settings):
    html = staff_client.get(url("dashboard:settings")).content.decode()
    assert 'name="default_delivery_fee"' not in html
    assert 'name="free_delivery_threshold"' not in html
    assert 'name="order_notification_email"' in html


def test_stored_delivery_settings_default_to_nothing(db):
    """Fresh settings carry no fee, so nothing stored can reintroduce one.

    The 0003 data migration zeroes the same two values on an existing row.
    """
    from core.models import SiteSettings

    settings_row = SiteSettings.load()
    assert settings_row.default_delivery_fee == Decimal("0.00")
    assert settings_row.free_delivery_threshold is None
