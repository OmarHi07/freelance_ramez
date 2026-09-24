import re
from decimal import Decimal
from urllib.parse import unquote, urlparse

import pytest
from django.core import mail
from django.urls import NoReverseMatch, reverse
from django.utils import translation

from cart.models import Cart, CartItem
from catalog.models import DiscountType
from conftest import make_product, make_promotion
from orders.models import Order, OrderStatus
from orders.services.whatsapp import (
    build_whatsapp_url,
    customer_order_whatsapp_url,
    customer_whatsapp_url,
    owner_order_url,
)

pytestmark = pytest.mark.django_db

ADDRESS = {"city": "Haifa", "street": "HaGefen", "building_number": "12", "phone": "050-123 4567"}


def url(name, lang="en", **kwargs):
    with translation.override(lang):
        return reverse(name, kwargs=kwargs or None)


def fill_cart(user, *lines):
    cart, _ = Cart.objects.get_or_create(user=user)
    for variant, quantity in lines:
        CartItem.objects.create(cart=cart, variant=variant, quantity=quantity)
    return cart


def place_order(client, **extra):
    data = {**ADDRESS, **extra}
    return client.post(url("orders:checkout"), data)


def test_checkout_requires_authentication(client, site_settings):
    response = client.get(url("orders:checkout"))
    assert response.status_code == 302
    assert "/account/login/" in response["Location"] and "next=" in response["Location"]


def test_empty_cart_redirects_to_cart(customer_client, site_settings):
    response = customer_client.get(url("orders:checkout"))
    assert response.status_code == 302
    assert response["Location"].endswith(url("cart:detail"))


def test_checkout_calculates_totals_on_server(customer_client, customer, site_settings):
    variant = make_product(price="40.00", stock=5).variants.first()
    make_promotion(value="25.00")
    fill_cart(customer, (variant, 2))
    # Browser-supplied totals must be ignored.
    response = place_order(customer_client, total="1.00", subtotal="1.00", discount_total="999")
    order = Order.objects.get()
    assert response.status_code == 302
    assert response["Location"].endswith(url("orders:confirmation", pk=order.pk))
    assert order.subtotal == Decimal("80.00")
    assert order.discount_total == Decimal("20.00")
    assert order.delivery_fee == Decimal("0.00")
    assert order.total == Decimal("60.00")  # subtotal minus discounts, no delivery
    assert order.status == OrderStatus.PENDING
    assert order.customer_phone == "0501234567"
    assert re.fullmatch(r"RNQ-\d{8}-[A-HJ-NP-Z2-9]{4}", order.number)
    assert order.status_history.get().to_status == OrderStatus.PENDING
    assert not CartItem.objects.filter(cart__user=customer).exists()


def test_stock_is_not_reduced_at_checkout(customer_client, customer, site_settings):
    variant = make_product(stock=5).variants.first()
    fill_cart(customer, (variant, 2))
    place_order(customer_client)
    variant.refresh_from_db()
    assert variant.stock_quantity == 5


def test_order_item_snapshots_do_not_change_later(customer_client, customer, site_settings):
    product = make_product(price="50.00", name_en="Pearl Drop", stock=5)
    variant = product.variants.first()
    promo = make_promotion(discount_type=DiscountType.FIXED, value="5.00")
    fill_cart(customer, (variant, 2))
    place_order(customer_client)
    order = Order.objects.get()
    item = order.items.get()

    product.regular_price = Decimal("99.00")
    product.name_en = "Renamed"
    product.save()
    promo.value = Decimal("30.00")
    promo.save()
    variant.delete()

    item.refresh_from_db()
    order.refresh_from_db()
    assert item.product_name_en == "Pearl Drop"
    assert item.original_unit_price == Decimal("50.00")
    assert item.unit_discount == Decimal("5.00")
    assert item.final_unit_price == Decimal("45.00")
    assert item.line_total == Decimal("90.00")
    assert item.variant is None and item.sku  # reference cleared, snapshot kept
    assert order.total == Decimal("90.00")  # products only; delivery is agreed later


def test_location_is_optional(customer_client, customer, site_settings):
    fill_cart(customer, (make_product().variants.first(), 1))
    place_order(customer_client)
    order = Order.objects.get()
    assert order.latitude is None and order.location_consent_at is None


def test_coordinates_without_consent_are_ignored(customer_client, customer, site_settings):
    fill_cart(customer, (make_product().variants.first(), 1))
    place_order(customer_client, latitude="32.79", longitude="34.98")
    assert Order.objects.get().latitude is None


def test_location_with_consent_is_stored_with_timestamp(customer_client, customer, site_settings):
    fill_cart(customer, (make_product().variants.first(), 1))
    place_order(
        customer_client, location_consent="True", latitude="32.794012", longitude="34.989571", location_accuracy="25"
    )
    order = Order.objects.get()
    assert order.latitude == Decimal("32.794012")
    assert order.longitude == Decimal("34.989571")
    assert order.location_accuracy_m == Decimal("25.0")
    assert order.location_consent_at is not None
    assert "google.com/maps" in order.google_maps_url


def test_out_of_range_coordinates_are_ignored(customer_client, customer, site_settings):
    fill_cart(customer, (make_product().variants.first(), 1))
    place_order(customer_client, location_consent="True", latitude="123", longitude="34.9")
    order = Order.objects.get()
    assert order.latitude is None


def test_missing_address_fields_are_rejected(customer_client, customer, site_settings):
    fill_cart(customer, (make_product().variants.first(), 1))
    response = customer_client.post(url("orders:checkout"), {"phone": "0501234567"})
    assert response.status_code == 200
    assert set(response.context["form"].errors) >= {"city", "street", "building_number"}
    assert not Order.objects.exists()


def test_saved_address_of_another_user_cannot_be_used(customer_client, customer, other_customer, site_settings):
    from accounts.models import Address

    foreign = Address.objects.create(user=other_customer, city="Akko", street="Secret", building_number="1")
    fill_cart(customer, (make_product().variants.first(), 1))
    response = customer_client.post(url("orders:checkout"), {"saved_address": foreign.pk, "phone": "0501234567"})
    assert response.status_code == 200
    assert "saved_address" in response.context["form"].errors
    assert not Order.objects.exists()


def test_checkout_blocks_when_stock_is_insufficient(customer_client, customer, site_settings):
    variant = make_product(stock=1).variants.first()
    fill_cart(customer, (variant, 1))
    variant.is_active = False
    variant.save()
    response = place_order(customer_client)
    assert response.status_code == 302
    assert not Order.objects.exists()


def test_users_cannot_see_each_others_orders(client, customer, other_customer, site_settings):
    fill_cart(customer, (make_product().variants.first(), 1))
    client.force_login(customer)
    place_order(client)
    order = Order.objects.get()
    client.force_login(other_customer)
    for name in ("orders:detail", "orders:confirmation"):
        assert client.get(url(name, pk=order.pk)).status_code == 404
    assert order.number not in client.get(url("orders:list")).content.decode()


def main_content(html: str) -> str:
    """Just the page body, without the shared header/footer contact links."""
    return html.split("<main", 1)[1].split("</main>", 1)[0]


def test_confirmation_page_has_no_customer_whatsapp_step(customer_client, customer, site_settings):
    fill_cart(customer, (make_product(price="30.00").variants.first(), 1))
    place_order(customer_client)
    order = Order.objects.get()
    html = customer_client.get(url("orders:confirmation", pk=order.pk)).content.decode()
    body = main_content(html)

    assert order.number in body
    # The customer is told the owner will get in touch, and sends nothing.
    assert "will contact you on WhatsApp" in body
    assert "Send order via WhatsApp" not in html
    assert "Next step" not in html
    # No way to send the order from this page. (The site footer still lists the
    # store's own WhatsApp as contact information, which is not an order action.)
    assert "wa.me" not in body
    assert "data-whatsapp-open" not in html
    assert "data-record-url" not in html
    # An owner dashboard URL must never reach a customer page.
    assert "/owner/" not in html
    assert str(order.pk) in body  # links to the customer's own order are fine


def test_confirmation_is_a_plain_get_with_no_notification_side_effects(customer_client, customer, site_settings):
    fill_cart(customer, (make_product().variants.first(), 1))
    place_order(customer_client)
    order = Order.objects.get()
    mail.outbox.clear()

    for _ in range(3):
        assert customer_client.get(url("orders:confirmation", pk=order.pk)).status_code == 200
    assert mail.outbox == []


def test_retired_whatsapp_opened_endpoint_is_gone(customer_client, customer, site_settings):
    fill_cart(customer, (make_product().variants.first(), 1))
    place_order(customer_client)
    order = Order.objects.get()
    with pytest.raises(NoReverseMatch):
        reverse("orders:whatsapp_opened", kwargs={"pk": order.pk})
    assert customer_client.post(f"/en/orders/{order.pk}/whatsapp-opened/").status_code == 404


def test_whatsapp_url_uses_international_number():
    assert build_whatsapp_url("972553003327", "hi there").startswith("https://wa.me/972553003327?text=hi%20there")
    with pytest.raises(ValueError):
        build_whatsapp_url("0553003327", "x")
    assert customer_whatsapp_url("055-300-3327") == "https://wa.me/972553003327"
    assert unquote(customer_whatsapp_url("+972 55 300 3327", "שלום")).endswith("שלום")


def test_prepared_customer_message_never_contains_the_owner_url(customer, site_settings):
    fill_cart(customer, (make_product().variants.first(), 1))
    order = Order.objects.create(
        customer=customer,
        number="RNQ-20260921-ZZ99",
        customer_name="Lina",
        customer_email=customer.email,
        customer_phone="0553003327",
        subtotal=Decimal("10.00"),
        discount_total=Decimal("0.00"),
        delivery_fee=Decimal("0.00"),
        total=Decimal("10.00"),
        language="en",
    )
    text = unquote(urlparse(customer_order_whatsapp_url(order)).query)
    assert "/owner/" not in text and "shop.example.test" not in text
    assert "Order link" not in text


def test_owner_link_requires_staff(client, customer, staff_user, site_settings):
    fill_cart(customer, (make_product().variants.first(), 1))
    client.force_login(customer)
    place_order(client)
    order = Order.objects.get()
    owner_path = owner_order_url(order).replace("https://shop.example.test", "")
    assert owner_path == f"/owner/orders/{order.pk}/"
    # The language-neutral link redirects to a language, then enforces staff access.
    assert client.get(owner_path, follow=True).status_code == 403
    client.logout()
    response = client.get(owner_path, follow=True)
    assert "/account/login/" in response.redirect_chain[-1][0]
    client.force_login(staff_user)
    assert client.get(owner_path, follow=True).status_code == 200
