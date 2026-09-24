"""WhatsApp click-to-chat message generation.

The website only *opens* WhatsApp with a prefilled message; it cannot know
whether the customer actually pressed send. The database order remains the
authoritative record.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from django.conf import settings
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext as _

from core.constants import BUSINESS_NAME
from core.formatting import format_money
from orders.models import Order

WA_BASE_URL = "https://wa.me/"


def normalize_international_number(number: str) -> str:
    digits = re.sub(r"\D", "", number or "")
    if not re.fullmatch(r"[1-9][0-9]{7,14}", digits):
        raise ValueError("WhatsApp number must be in international format, digits only (e.g. 972553003327).")
    return digits


def build_whatsapp_url(international_number: str, message: str) -> str:
    return f"{WA_BASE_URL}{normalize_international_number(international_number)}?text={quote(message, safe='')}"


def _strip_language_prefix(path: str) -> str:
    for code, _name in settings.LANGUAGES:
        prefix = f"/{code}/"
        if path.startswith(prefix):
            return "/" + path[len(prefix) :]
    return path


def owner_order_url(order: Order, request=None) -> str:
    """Absolute, language-neutral URL of the order in the owner dashboard.

    The page itself requires a logged-in staff account; knowing the URL is
    never enough to see the order.
    """
    path = _strip_language_prefix(reverse("dashboard:order_detail", kwargs={"pk": order.pk}))
    if settings.SITE_URL:
        return f"{settings.SITE_URL}{path}"
    if request is not None:
        return request.build_absolute_uri(path)
    return path


def build_order_message(order: Order, owner_url: str, language: str | None = None) -> str:
    language = language or order.language or settings.LANGUAGE_CODE
    with translation.override(language):
        lines = [
            _("New %(store)s order") % {"store": BUSINESS_NAME},
            _("Order number: %(number)s") % {"number": order.number},
            _("Customer: %(name)s") % {"name": order.customer_name},
            _("Total: %(total)s") % {"total": format_money(order.total)},
            _("Order link (staff only): %(url)s") % {"url": owner_url},
        ]
    return "\n".join(lines)


def customer_whatsapp_url(phone: str, message: str = "") -> str:
    """wa.me link to message a customer from the dashboard (Israeli local numbers supported)."""
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = "972" + digits[1:]
    try:
        number = normalize_international_number(digits)
    except ValueError:
        return ""
    url = f"{WA_BASE_URL}{number}"
    return f"{url}?text={quote(message, safe='')}" if message else url
