"""Owner notification service.

When an order commits, the owner is emailed at the address configured in
``/owner/settings/``. The email carries the full order and two buttons: open
the order in the (staff-only) dashboard, and open WhatsApp with a prepared
message to that customer.

Design notes
------------
* Sending is scheduled with ``transaction.on_commit``, so nothing is emailed
  for an order that was rolled back, and a page refresh never resends.
* A failure is recorded and logged but never propagates: the customer's order
  is already saved and must stay valid.
* Logs carry the order number and the outcome only — never the recipient, the
  customer's name, phone, address, location or the message body.
* No queue is involved: Django's own email framework sends the message inline
  after the commit, with ``EMAIL_TIMEOUT`` bounding a slow SMTP server.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone, translation

from core.models import get_site_settings
from orders.models import Order
from orders.services import whatsapp

logger = logging.getLogger("rawnaq.orders")


@dataclass(frozen=True)
class NotificationResult:
    """Outcome of one attempt. ``reason`` is a short code, never customer data."""

    sent: bool
    reason: str = ""

    @property
    def not_configured(self) -> bool:
        return self.reason == "not_configured"


def owner_notification_address(request=None) -> str:
    """The configured owner address, or ``""`` when notifications are off."""
    return (get_site_settings(request).order_notification_email or "").strip()


def build_owner_email(order: Order, recipient: str, request=None) -> EmailMultiAlternatives:
    """Render the plain-text and HTML owner notification for ``order``."""
    context = {
        "order": order,
        "items": list(order.items.all()),
        "owner_url": whatsapp.owner_order_url(order, request),
        "whatsapp_url": whatsapp.customer_order_whatsapp_url(order),
        "whatsapp_message": whatsapp.customer_message(order),
        "products_total": order.items_total,
    }
    # The owner reads the email in the language the order was placed in.
    language = "en" if (order.language or "ar").startswith("en") else "ar"
    with translation.override(language):
        subject = render_to_string("orders/emails/new_order_owner_subject.txt", context).strip()
        text_body = render_to_string("orders/emails/new_order_owner.txt", context)
        html_body = render_to_string("orders/emails/new_order_owner.html", context)

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
        connection=get_connection(timeout=settings.EMAIL_TIMEOUT),
    )
    message.attach_alternative(html_body, "text/html")
    return message


def send_new_order_email(order: Order, *, request=None) -> NotificationResult:
    """Email the owner about ``order``. Never raises.

    Records the attempt either way, so the dashboard can show "sent" or
    "not sent" and offer a resend.
    """
    recipient = owner_notification_address(request)
    if not recipient:
        logger.warning(
            "Owner notification skipped: no address configured",
            extra={"event": "owner_email_not_configured", "order_number": order.number},
        )
        return NotificationResult(sent=False, reason="not_configured")

    attempted_at = timezone.now()
    try:
        build_owner_email(order, recipient, request).send(fail_silently=False)
    except Exception:
        # Deliberately broad: no email problem may affect a saved order.
        Order.objects.filter(pk=order.pk).update(owner_notification_attempted_at=attempted_at)
        order.owner_notification_attempted_at = attempted_at
        logger.exception(
            "Owner notification failed",
            extra={"event": "owner_email_failed", "order_number": order.number},
        )
        return NotificationResult(sent=False, reason="send_failed")

    sent_at = timezone.now()
    Order.objects.filter(pk=order.pk).update(
        owner_notification_attempted_at=attempted_at, owner_notification_sent_at=sent_at
    )
    order.owner_notification_attempted_at = attempted_at
    order.owner_notification_sent_at = sent_at
    logger.info("Owner notification sent", extra={"event": "owner_email_sent", "order_number": order.number})
    return NotificationResult(sent=True)


def schedule_new_order_email(order: Order, *, request=None) -> None:
    """Queue the owner email to go out once the current transaction commits.

    Called from the checkout service inside its ``atomic`` block. If the
    transaction rolls back the callback is dropped and nothing is sent.
    """
    transaction.on_commit(lambda: send_new_order_email(order, request=request))
