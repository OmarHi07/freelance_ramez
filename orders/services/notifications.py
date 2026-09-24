"""Owner notification interface.

Version 1 uses :class:`ClickToChatNotifier`: the customer taps a button that
opens WhatsApp with a prefilled message to the store. Nothing is sent by the
server and no Meta credentials are needed.

To move to the official WhatsApp Business Platform (Cloud API) later, add a
``CloudApiNotifier`` implementing :class:`OrderNotifier` that sends an approved
template message to the owner's number from a background job, and point
``ORDER_NOTIFIER_BACKEND`` at it. Views only depend on this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django.utils.module_loading import import_string

from core.models import get_site_settings
from orders.models import Order
from orders.services import whatsapp


@dataclass(frozen=True)
class NotificationResult:
    channel: str
    delivered_by_server: bool
    action_url: str = ""
    message: str = ""


class OrderNotifier(ABC):
    channel = "base"

    @abstractmethod
    def new_order(self, order: Order, *, request=None) -> NotificationResult:
        """Prepare or send the "new order" notification for the store owner."""


class ClickToChatNotifier(OrderNotifier):
    """Builds a ``wa.me`` link. Opening it does not guarantee a message was sent."""

    channel = "whatsapp_click_to_chat"

    def new_order(self, order: Order, *, request=None) -> NotificationResult:
        number = get_site_settings(request).whatsapp_number
        message = whatsapp.build_order_message(order, whatsapp.owner_order_url(order, request))
        return NotificationResult(
            channel=self.channel,
            delivered_by_server=False,
            action_url=whatsapp.build_whatsapp_url(number, message),
            message=message,
        )


def get_notifier() -> OrderNotifier:
    return import_string(settings.ORDER_NOTIFIER_BACKEND)()


def record_whatsapp_opened(order: Order) -> bool:
    """Record the first time the customer pressed the WhatsApp button.

    This is *not* proof that a message was sent. Returns True if recorded now.
    """
    updated = Order.objects.filter(Q(pk=order.pk) & Q(whatsapp_opened_at__isnull=True)).update(
        whatsapp_opened_at=timezone.now()
    )
    return bool(updated)
