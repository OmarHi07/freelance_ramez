"""WhatsApp click-to-chat links, used by the owner only.

The customer never opens WhatsApp. After an order is placed the owner gets an
email with a button that opens a chat **with that customer**, carrying a
prepared message about payment and delivery. Nothing is sent automatically:
the owner reads the draft and presses Send inside WhatsApp.

Nothing here may leak a dashboard URL into a message addressed to a customer.
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
DEFAULT_COUNTRY_CODE = "972"  # Israel


def normalize_international_number(number: str) -> str:
    digits = re.sub(r"\D", "", number or "")
    if not re.fullmatch(r"[1-9][0-9]{7,14}", digits):
        raise ValueError("WhatsApp number must be in international format, digits only (e.g. 972553003327).")
    return digits


def to_international(phone: str) -> str:
    """Turn a number the customer typed into digits WhatsApp accepts.

    Handles the shapes customers actually use::

        0553003327     -> 972553003327   (local, leading zero dropped)
        +972553003327  -> 972553003327
        00972553003327 -> 972553003327
        972553003327   -> 972553003327

    Returns ``""`` when no usable number can be built, so callers can hide the
    button instead of producing a broken link.
    """
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return ""
    if digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = DEFAULT_COUNTRY_CODE + digits[1:]
    try:
        return normalize_international_number(digits)
    except ValueError:
        return ""


def build_whatsapp_url(international_number: str, message: str) -> str:
    return f"{WA_BASE_URL}{normalize_international_number(international_number)}?text={quote(message, safe='')}"


def customer_whatsapp_url(phone: str, message: str = "") -> str:
    """``wa.me`` link for a customer number, or ``""`` when it cannot be built."""
    number = to_international(phone)
    if not number:
        return ""
    url = f"{WA_BASE_URL}{number}"
    # quote() percent-encodes the whole Unicode message, emoji and Arabic included.
    return f"{url}?text={quote(message, safe='')}" if message else url


def _strip_language_prefix(path: str) -> str:
    for code, _name in settings.LANGUAGES:
        prefix = f"/{code}/"
        if path.startswith(prefix):
            return "/" + path[len(prefix) :]
    return path


def owner_order_url(order: Order, request=None) -> str:
    """Absolute, language-neutral URL of the order in the owner dashboard.

    Only ever used inside the private owner notification email and the owner
    dashboard. The page itself requires a logged-in staff account, so knowing
    the URL is never enough to see the order.
    """
    path = _strip_language_prefix(reverse("dashboard:order_detail", kwargs={"pk": order.pk}))
    if settings.SITE_URL:
        return f"{settings.SITE_URL}{path}"
    if request is not None:
        return request.build_absolute_uri(path)
    return path


def customer_message(order: Order) -> str:
    """The draft the owner sends to the customer, in the order's language.

    It opens the conversation about payment and delivery. It deliberately
    contains no dashboard URL and no internal notes.
    """
    language = order.language or settings.LANGUAGE_CODE
    with translation.override("en" if language.startswith("en") else "ar"):
        lines = [
            _("Hello %(name)s 🌸") % {"name": order.customer_name},
            "",
            _("Thank you for your order from %(store)s.") % {"store": BUSINESS_NAME},
            "",
            _("Order number: %(number)s") % {"number": order.number},
            _("Products total: %(total)s") % {"total": format_money(order.items_total)},
            _("Delivery is not included yet."),
            "",
            _("Which payment method do you prefer?"),
            _("• Cash"),
            _("• Bit"),
            _("• Bank transfer"),
            "",
            _("We will also confirm the delivery cost and delivery time with you here."),
        ]
    return "\n".join(lines)


def customer_order_whatsapp_url(order: Order) -> str:
    """Chat with this order's customer, prefilled with the payment/delivery draft.

    Empty when the stored phone number cannot be turned into a WhatsApp number;
    callers then show the raw number and a warning instead of a dead button.
    """
    return customer_whatsapp_url(order.customer_phone, customer_message(order))
