"""The owner is emailed after an order commits, and starts the WhatsApp chat."""

import re
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
from django.core import mail
from django.db import transaction
from django.urls import reverse
from django.utils import translation

from cart.models import Cart, CartItem
from conftest import make_product, make_user
from core.constants import BUSINESS_NAME
from core.models import SiteSettings
from orders.models import Order, OrderStatus
from orders.services.notifications import send_new_order_email
from orders.services.whatsapp import customer_message, customer_order_whatsapp_url, to_international

pytestmark = pytest.mark.django_db

ADDRESS = {"city": "Haifa", "street": "HaGefen", "building_number": "12", "phone": "050-123 4567"}


def url(name, lang="en", **kwargs):
    with translation.override(lang):
        return reverse(name, kwargs=kwargs or None)


def checkout(client, user, capture, *, price="30.00", quantity=1, **extra) -> Order:
    """Place an order and run the on-commit callbacks the test transaction defers.

    Tests run inside a transaction that is never committed, so
    ``django_capture_on_commit_callbacks`` stands in for the real commit.
    """
    cart, _ = Cart.objects.get_or_create(user=user)
    CartItem.objects.create(cart=cart, variant=make_product(price=price).variants.first(), quantity=quantity)
    with capture(execute=True):
        client.post(url("orders:checkout"), {**ADDRESS, **extra})
    return Order.objects.latest("created_at")


@pytest.fixture
def owner_client(staff_user):
    """A separate staff session.

    ``staff_client`` and ``customer_client`` share one ``client`` fixture, so a
    test that needs both logged in at once must build its own.
    """
    from django.test import Client

    session = Client()
    session.force_login(staff_user)
    return session


@pytest.fixture
def place_order(django_capture_on_commit_callbacks):
    """``place_order(client, user, price=..., quantity=...)`` -> the created Order."""

    def _place(client, user, **kwargs):
        return checkout(client, user, django_capture_on_commit_callbacks, **kwargs)

    return _place


def html_part(message) -> str:
    return next(body for body, mime in message.alternatives if mime == "text/html")


# ---------------------------------------------------------------------------
# When the email goes out
# ---------------------------------------------------------------------------
def test_one_order_produces_exactly_one_owner_email(customer_client, customer, site_settings, place_order):
    mail.outbox.clear()
    order = place_order(customer_client, customer)

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == [site_settings.order_notification_email]
    assert order.number in message.subject
    assert BUSINESS_NAME in message.subject
    assert "New order" in message.subject

    order.refresh_from_db()
    assert order.owner_notification_sent_at is not None
    assert order.owner_notification_attempted_at is not None


@pytest.mark.django_db(transaction=True)
def test_the_email_is_only_sent_after_the_transaction_commits(customer, site_settings):
    """Nothing leaves the server while the checkout transaction is still open."""
    from orders.services.creation import DeliveryDetails, create_order_from_cart

    cart, _ = Cart.objects.get_or_create(user=customer)
    CartItem.objects.create(cart=cart, variant=make_product().variants.first(), quantity=1)
    mail.outbox.clear()

    with transaction.atomic():  # outer block: the inner commit is deferred
        create_order_from_cart(
            user=customer,
            cart=cart,
            delivery=DeliveryDetails(city="Haifa", street="HaGefen", building_number="1"),
            phone="0501234567",
        )
        assert mail.outbox == [], "the email must wait for the commit"
    assert len(mail.outbox) == 1


@pytest.mark.django_db(transaction=True)
def test_a_rolled_back_checkout_sends_nothing(customer, site_settings):
    from orders.services.creation import DeliveryDetails, create_order_from_cart

    cart, _ = Cart.objects.get_or_create(user=customer)
    CartItem.objects.create(cart=cart, variant=make_product().variants.first(), quantity=1)
    mail.outbox.clear()

    class Rollback(Exception):
        pass

    with pytest.raises(Rollback), transaction.atomic():
        create_order_from_cart(
            user=customer,
            cart=cart,
            delivery=DeliveryDetails(city="Haifa", street="HaGefen", building_number="1"),
            phone="0501234567",
        )
        raise Rollback
    assert mail.outbox == []
    assert not Order.objects.exists()


def test_refreshing_the_confirmation_page_never_resends(customer_client, customer, site_settings, place_order):
    order = place_order(customer_client, customer)
    assert len(mail.outbox) == 1
    for _ in range(4):
        assert customer_client.get(url("orders:confirmation", pk=order.pk)).status_code == 200
    assert len(mail.outbox) == 1


def test_email_failure_keeps_the_order_and_is_recorded(
    customer_client, customer, site_settings, monkeypatch, place_order
):
    from orders.services import notifications

    def explode(*args, **kwargs):
        raise OSError("smtp is down")

    monkeypatch.setattr(notifications.EmailMultiAlternatives, "send", explode)
    mail.outbox.clear()
    order = place_order(customer_client, customer)

    assert Order.objects.filter(pk=order.pk).exists(), "an email problem must never lose an order"
    order.refresh_from_db()
    assert order.status == OrderStatus.PENDING
    assert order.owner_notification_attempted_at is not None
    assert order.owner_notification_sent_at is None
    assert order.owner_notification_failed is True
    assert mail.outbox == []


def test_checkout_succeeds_when_no_notification_address_is_configured(
    customer_client, customer, site_settings, place_order
):
    site_settings.order_notification_email = ""
    site_settings.save()
    mail.outbox.clear()

    order = place_order(customer_client, customer)
    assert order.pk and order.status == OrderStatus.PENDING
    assert mail.outbox == []
    order.refresh_from_db()
    assert order.owner_notification_sent_at is None
    # Nothing was attempted, so the order is not marked as a failure.
    assert order.owner_notification_attempted_at is None
    assert order.owner_notification_failed is False


def test_notification_logs_carry_no_customer_data(
    customer_client, customer, site_settings, monkeypatch, caplog, place_order
):
    from orders.services import notifications

    monkeypatch.setattr(
        notifications.EmailMultiAlternatives, "send", lambda *a, **k: (_ for _ in ()).throw(OSError("nope"))
    )
    with caplog.at_level("INFO", logger="rawnaq.orders"):
        order = place_order(customer_client, customer)
    text = "\n".join(record.getMessage() for record in caplog.records)
    assert order.customer_email not in text
    assert order.customer_phone not in text
    assert order.customer_name not in text
    assert site_settings.order_notification_email not in text


# ---------------------------------------------------------------------------
# What the email contains
# ---------------------------------------------------------------------------
def test_owner_email_contains_the_order_details(customer_client, customer, site_settings, place_order):
    mail.outbox.clear()
    order = place_order(customer_client, customer, price="45.50", quantity=2, customer_notes="Please gift wrap")
    message = mail.outbox[0]
    item = order.items.get()

    for body in (message.body, html_part(message)):
        assert order.number in body
        assert order.customer_name in body
        assert order.customer_phone in body
        assert order.customer_email in body
        assert order.city in body and order.street in body
        assert "Please gift wrap" in body
        assert item.product_name_en in body
        assert item.variant_name_en in body
        assert str(item.quantity) in body
        assert "₪45.50" in body  # unit price
        assert "₪91.00" in body  # line total and products total
        assert order.get_status_display() in body
        assert "not included" in body  # the delivery warning


def test_owner_email_links_to_the_protected_dashboard_page(
    client, customer_client, customer, staff_user, site_settings, place_order
):
    mail.outbox.clear()
    order = place_order(customer_client, customer)
    message = mail.outbox[0]

    owner_url = f"https://shop.example.test/owner/orders/{order.pk}/"
    assert owner_url in message.body
    assert owner_url in html_part(message)

    # The link is useless without a staff login.
    path = f"/owner/orders/{order.pk}/"
    client.force_login(customer)
    assert client.get(path, follow=True).status_code == 403
    client.logout()
    assert "/account/login/" in client.get(path, follow=True).redirect_chain[-1][0]
    client.force_login(staff_user)
    assert client.get(path, follow=True).status_code == 200


def test_owner_email_has_a_whatsapp_button_for_the_customers_number(
    customer_client, customer, site_settings, place_order
):
    mail.outbox.clear()
    place_order(customer_client, customer)
    html = html_part(mail.outbox[0])

    assert "Message customer on WhatsApp" in html
    link = re.search(r'href="(https://wa\.me/[^"]+)"', html).group(1)
    parsed = urlparse(link)
    # The customer's own number, not the store's.
    assert parsed.path == "/972501234567"
    assert parsed.path != "/972553003327"


def test_owner_email_escapes_customer_supplied_html(customer_client, site_settings, place_order):
    attacker = make_user(email="xss@example.test")
    attacker.full_name = '<img src=x onerror="alert(1)">'
    attacker.save()
    customer_client.force_login(attacker)
    mail.outbox.clear()
    place_order(customer_client, attacker, customer_notes="<script>alert('notes')</script>")

    html = html_part(mail.outbox[0])
    assert "<img src=x" not in html
    assert "<script>alert(" not in html
    assert "&lt;img src=x" in html
    assert "&lt;script&gt;" in html


def test_owner_email_shows_a_warning_instead_of_a_broken_whatsapp_button(
    customer_client, customer, site_settings, place_order
):
    mail.outbox.clear()
    order = place_order(customer_client, customer)
    Order.objects.filter(pk=order.pk).update(customer_phone="12")
    order.refresh_from_db()
    mail.outbox.clear()

    send_new_order_email(order)
    html = html_part(mail.outbox[0])
    assert "Message customer on WhatsApp" not in html
    assert "WhatsApp could not be opened" in html
    assert "https://wa.me/" not in html
    assert Order.objects.filter(pk=order.pk).exists()  # the order stays valid


# ---------------------------------------------------------------------------
# The prepared WhatsApp message
# ---------------------------------------------------------------------------
def make_order(**kwargs) -> Order:
    defaults = {
        "number": "RNQ-20260921-AB12",
        "customer_name": "Lina",
        "customer_email": "lina@example.test",
        "customer_phone": "0553003327",
        "subtotal": Decimal("120.00"),
        "discount_total": Decimal("20.00"),
        "delivery_fee": Decimal("0.00"),
        "total": Decimal("100.00"),
        "language": "en",
    }
    defaults.update(kwargs)
    return Order(**defaults)


def test_english_message_asks_about_payment_and_delivery():
    text = customer_message(make_order(language="en"))
    assert "Hello Lina" in text
    assert BUSINESS_NAME in text
    assert "RNQ-20260921-AB12" in text
    assert "₪100.00" in text  # products total, after discounts
    assert "Delivery is not included yet." in text
    assert "Cash" in text and "Bit" in text and "Bank transfer" in text
    assert "delivery cost and delivery time" in text


def test_arabic_message_is_generated_from_the_order_language():
    text = customer_message(make_order(language="ar"))
    assert "مرحباً Lina" in text
    assert BUSINESS_NAME in text
    assert "نقداً" in text and "Bit" in text and "تحويل بنكي" in text
    assert "رسوم التوصيل غير مشمولة بعد." in text
    assert "Cash" not in text


def test_the_message_never_carries_an_owner_or_admin_url_or_internal_notes():
    order = make_order(internal_notes="Owner only: call supplier first")
    for language in ("ar", "en"):
        order.language = language
        text = customer_message(order)
        assert "/owner/" not in text
        assert "Order link" not in text
        assert "shop.example.test" not in text
        assert "call supplier first" not in text


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("0553003327", "972553003327"),
        ("+972553003327", "972553003327"),
        ("00972553003327", "972553003327"),
        ("972553003327", "972553003327"),
        ("055-300 3327", "972553003327"),
        ("+972 55 300 3327", "972553003327"),
    ],
)
def test_phone_formats_normalize_to_one_wa_me_number(typed, expected):
    assert to_international(typed) == expected
    url_for_order = customer_order_whatsapp_url(make_order(customer_phone=typed))
    assert urlparse(url_for_order).path == f"/{expected}"


@pytest.mark.parametrize("bad", ["", "   ", "12", "abc", "+++", "0"])
def test_invalid_phone_numbers_produce_no_button(bad):
    assert to_international(bad) == ""
    assert customer_order_whatsapp_url(make_order(customer_phone=bad)) == ""


def test_the_whole_unicode_message_is_url_encoded():
    link = customer_order_whatsapp_url(make_order(language="ar"))
    query = urlparse(link).query
    assert " " not in query and "\n" not in query
    decoded = parse_qs(query)["text"][0]
    assert "🌸" in decoded and "مرحباً" in decoded


# ---------------------------------------------------------------------------
# Resending from the dashboard
# ---------------------------------------------------------------------------
def test_staff_can_resend_the_owner_email(owner_client, customer_client, customer, site_settings, place_order):
    order = place_order(customer_client, customer)
    mail.outbox.clear()

    target = url("dashboard:order_resend_email", pk=order.pk)
    response = owner_client.post(target, follow=True)
    assert response.status_code == 200
    assert len(mail.outbox) == 1
    assert order.number in mail.outbox[0].subject
    assert any("sent again" in str(m) for m in response.context["messages"])


def test_resending_never_changes_the_order_status_or_stock(
    owner_client, customer_client, customer, site_settings, place_order
):
    order = place_order(customer_client, customer, quantity=2)
    variant = order.items.get().variant
    before = (order.status, variant.stock_quantity, order.stock_deducted_at)

    owner_client.post(url("dashboard:order_resend_email", pk=order.pk))
    order.refresh_from_db()
    variant.refresh_from_db()
    assert (order.status, variant.stock_quantity, order.stock_deducted_at) == before


def test_resend_is_post_only(owner_client, customer_client, customer, site_settings, place_order):
    order = place_order(customer_client, customer)
    assert owner_client.get(url("dashboard:order_resend_email", pk=order.pk)).status_code == 405


def test_resend_requires_csrf(client, staff_user, customer_client, customer, site_settings, place_order):
    from django.test import Client

    order = place_order(customer_client, customer)
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(staff_user)
    mail.outbox.clear()
    assert strict.post(url("dashboard:order_resend_email", pk=order.pk)).status_code == 403
    assert mail.outbox == []


def test_customers_cannot_reach_the_resend_endpoint(client, customer_client, customer, site_settings, place_order):
    order = place_order(customer_client, customer)
    target = url("dashboard:order_resend_email", pk=order.pk)
    mail.outbox.clear()

    assert customer_client.post(target).status_code == 403
    client.logout()
    assert "/account/login/" in client.post(target)["Location"]
    assert mail.outbox == []


def test_resend_reports_a_missing_notification_address(
    owner_client, customer_client, customer, site_settings, place_order
):
    order = place_order(customer_client, customer)
    SiteSettings.objects.update(order_notification_email="")
    mail.outbox.clear()

    response = owner_client.post(url("dashboard:order_resend_email", pk=order.pk), follow=True)
    assert mail.outbox == []
    assert any("No notification email address is set" in str(m) for m in response.context["messages"])


# ---------------------------------------------------------------------------
# What the owner dashboard shows
# ---------------------------------------------------------------------------
def test_owner_order_page_shows_the_notification_state_and_prepared_message(
    owner_client, customer_client, customer, site_settings, place_order
):
    order = place_order(customer_client, customer)
    html = owner_client.get(url("dashboard:order_detail", pk=order.pk)).content.decode()

    assert "Order email" in html and "Sent" in html
    assert "Resend owner email" in html
    assert "Message customer on WhatsApp" in html
    assert "wa.me/972501234567" in html
    # The customer no longer opens WhatsApp, so that wording is gone.
    assert "Customer opened WhatsApp" not in html
    assert "Products total" in html
    assert "Delivery is not included" in html


def test_owner_order_page_warns_when_the_phone_cannot_be_used(
    owner_client, customer_client, customer, site_settings, place_order
):
    order = place_order(customer_client, customer)
    Order.objects.filter(pk=order.pk).update(customer_phone="12")
    html = owner_client.get(url("dashboard:order_detail", pk=order.pk)).content.decode()
    assert "WhatsApp cannot be opened" in html
    assert "wa.me" not in html.split("<main", 1)[1].split("</main>", 1)[0]


def test_dashboard_warns_when_no_notification_address_is_configured(staff_client, site_settings):
    SiteSettings.objects.update(order_notification_email="")
    html = staff_client.get(url("dashboard:overview")).content.decode()
    assert "no notification address is set" in html

    SiteSettings.objects.update(order_notification_email="owner@example.test")
    html = staff_client.get(url("dashboard:overview")).content.decode()
    assert "no notification address is set" not in html


def test_the_notification_address_is_never_shown_to_customers(customer_client, customer, site_settings, place_order):
    order = place_order(customer_client, customer)
    for path in (
        url("orders:confirmation", pk=order.pk),
        url("orders:detail", pk=order.pk),
        url("orders:list"),
        "/en/",
    ):
        assert site_settings.order_notification_email not in customer_client.get(path).content.decode(), path
