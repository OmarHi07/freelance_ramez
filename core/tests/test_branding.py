"""The official business name is `rawnaq_accessories1`, everywhere, in both languages."""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.core import mail
from django.urls import reverse
from django.utils import translation

from conftest import PASSWORD, make_brand, make_product, make_user
from core.constants import BUSINESS_NAME
from core.models import SiteSettings
from orders.models import Order
from orders.services.notifications import ClickToChatNotifier

pytestmark = pytest.mark.django_db

# Spellings the business has moved away from. They must not reach a visitor.
OBSOLETE_NAMES = ["Rawnaq Accessories", "Rawnaq owner", "رونق للإكسسوارات", "رونق"]

STOREFRONT_PATHS = ["/ar/", "/en/", "/ar/brands/", "/en/brands/", "/ar/cart/", "/en/account/login/"]


def assert_no_obsolete_names(html: str, where: str) -> None:
    for name in OBSOLETE_NAMES:
        assert name not in html, f"{where} still shows the old business name {name!r}"


def test_the_canonical_name_has_the_exact_required_spelling():
    assert BUSINESS_NAME == "rawnaq_accessories1"


def test_storefront_pages_show_the_official_name_in_both_languages(client, site_settings):
    make_product(make_brand())
    for path in STOREFRONT_PATHS:
        html = client.get(path).content.decode()
        assert BUSINESS_NAME in html, path
        assert_no_obsolete_names(html, path)


def test_arabic_pages_render_the_name_left_to_right(client, site_settings):
    html = client.get("/ar/").content.decode()
    # The header and footer wordmarks carry dir="ltr" so the underscore and
    # digit are not reordered by the RTL layout.
    assert re.search(r'dir="ltr"[^>]*>\s*' + re.escape(BUSINESS_NAME), html)


def test_page_titles_and_metadata_use_the_official_name(client, site_settings):
    for path in ("/ar/", "/en/"):
        html = client.get(path).content.decode()
        title = re.search(r"<title>(.*?)</title>", html, re.S).group(1)
        assert BUSINESS_NAME in title, path
        assert_no_obsolete_names(title, f"{path} <title>")


def test_owner_dashboard_uses_the_official_name(staff_client, site_settings):
    with translation.override("en"):
        html = staff_client.get(reverse("dashboard:overview")).content.decode()
    assert BUSINESS_NAME in html
    assert_no_obsolete_names(html, "owner dashboard")


def test_django_technical_admin_headings_use_the_official_name(client, site_settings):
    superuser = make_user(email="root-branding@example.test", is_staff=True, is_superuser=True)
    client.force_login(superuser)
    html = client.get("/django-admin/").content.decode()
    assert f"{BUSINESS_NAME} · Technical admin" in html
    assert_no_obsolete_names(html, "django admin")


def test_registration_message_uses_the_official_name(client, site_settings):
    response = client.post(
        "/en/account/register/",
        {
            "full_name": "New Customer",
            "email": "new-customer@example.test",
            "phone": "0501234567",
            "password1": PASSWORD,
            "password2": PASSWORD,
        },
        follow=True,
    )
    html = response.content.decode()
    assert f"Welcome to {BUSINESS_NAME}" in html
    assert_no_obsolete_names(html, "registration message")


def test_password_reset_email_uses_the_official_name(client, site_settings):
    make_user(email="reset-me@example.test")
    with translation.override("en"):
        target = reverse("accounts:password_reset")
    client.post(target, {"email": "reset-me@example.test"})
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    body = message.subject + "\n" + message.body
    assert BUSINESS_NAME in message.subject
    assert BUSINESS_NAME in message.body
    assert_no_obsolete_names(body, "password reset email")


def test_email_sender_display_name_uses_the_official_name():
    assert settings.DEFAULT_FROM_EMAIL.startswith(BUSINESS_NAME)
    assert settings.SERVER_EMAIL == settings.DEFAULT_FROM_EMAIL


@pytest.mark.parametrize("language", ["ar", "en"])
def test_whatsapp_order_message_uses_the_official_name(site_settings, language):
    order = Order(
        number="RNQ-20260921-AB12",
        customer_name="Lina",
        customer_email="l@example.test",
        customer_phone="050",
        total="10.00",
        language=language,
    )
    message = ClickToChatNotifier().new_order(order).message
    assert BUSINESS_NAME in message
    assert_no_obsolete_names(message, f"WhatsApp message ({language})")


def test_order_confirmation_page_uses_the_official_name(client, site_settings, customer):
    order = Order.objects.create(
        customer=customer,
        number="RNQ-20260921-CD34",
        customer_name="Lina",
        customer_email=customer.email,
        customer_phone="0501234567",
        subtotal="10.00",
        discount_total="0.00",
        delivery_fee="0.00",
        total="10.00",
        language="ar",
    )
    client.force_login(customer)
    html = client.get(reverse("orders:confirmation", kwargs={"pk": order.pk})).content.decode()
    assert BUSINESS_NAME in html
    assert_no_obsolete_names(html, "order confirmation")


# ---------------------------------------------------------------------------
# Defaults, the stored singleton, and the owner settings form
# ---------------------------------------------------------------------------
def test_site_settings_defaults_and_stored_row_use_the_official_name(db):
    assert SiteSettings._meta.get_field("store_name_ar").default == BUSINESS_NAME
    assert SiteSettings._meta.get_field("store_name_en").default == BUSINESS_NAME
    stored = SiteSettings.load()
    assert stored.store_name_ar == BUSINESS_NAME
    assert stored.store_name_en == BUSINESS_NAME


def test_owner_cannot_rename_the_business_from_the_settings_page(staff_client, site_settings):
    from dashboard.forms import SiteSettingsForm

    assert "store_name_ar" not in SiteSettingsForm.Meta.fields
    assert "store_name_en" not in SiteSettingsForm.Meta.fields

    with translation.override("en"):
        target = reverse("dashboard:settings")
    response = staff_client.post(
        target,
        {
            "store_name_ar": "Something else",
            "store_name_en": "Something else",
            "whatsapp_number": "972553003327",
            "whatsapp_display_number": "0553003327",
            "instagram_url": f"https://www.instagram.com/{BUSINESS_NAME}/",
            "default_delivery_fee": "20.00",
        },
    )
    assert response.status_code == 302
    site_settings.refresh_from_db()
    assert site_settings.store_name_en == BUSINESS_NAME
    assert site_settings.store_name_ar == BUSINESS_NAME


def test_settings_page_shows_the_official_name_as_read_only(staff_client, site_settings):
    with translation.override("en"):
        html = staff_client.get(reverse("dashboard:settings")).content.decode()
    assert BUSINESS_NAME in html
    assert 'name="store_name_en"' not in html
    assert 'name="store_name_ar"' not in html


def test_no_obsolete_business_name_is_left_in_user_facing_templates():
    """Technical identifiers may keep the word; visible copy may not."""
    template_root = Path(settings.BASE_DIR) / "templates"
    offenders = []
    for template in template_root.rglob("*"):
        if template.suffix not in {".html", ".txt"}:
            continue
        text = template.read_text(encoding="utf-8")
        # `{% load ... rawnaq %}` is the template-tag library, not the business name.
        text = re.sub(r"{%\s*load[^%]*%}", "", text)
        for name in OBSOLETE_NAMES:
            if name in text:
                offenders.append(f"{template.relative_to(template_root)}: {name}")
    assert not offenders, offenders
