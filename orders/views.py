from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from accounts.models import Address
from cart import services as cart_services
from orders.forms import ADDRESS_FIELDS, CheckoutForm
from orders.models import Order, OrderStatus
from orders.services.creation import CheckoutError, DeliveryDetails, SharedLocation, create_order_from_cart
from orders.services.notifications import get_notifier, record_whatsapp_opened
from orders.services.status import PROGRESS_STEPS

ORDERS_PAGE_SIZE = 10


def _checkout_error_message(error: CheckoutError) -> str:
    names = ", ".join(error.products)
    if error.code == "unavailable":
        return _("Some items are no longer available: %(names)s. Please review your cart.") % {"names": names}
    if error.code == "insufficient_stock":
        return _("Not enough stock for: %(names)s. Please review your cart.") % {"names": names}
    if error.code == "empty":
        return _("Your cart is empty.")
    return _("We could not place your order. Please try again.")


@login_required
@require_http_methods(["GET", "POST"])
def checkout(request):
    cart = cart_services.get_cart(request)
    if cart is None or not cart.items.exists():
        messages.info(request, _("Your cart is empty."))
        return redirect("cart:detail")
    adjusted = cart_services.normalize_cart(cart)
    cart_view = cart_services.build_cart_view(request, cart)
    if adjusted or cart_view.problems or any(item.exceeds_stock for item in cart_view.items):
        messages.warning(request, _("Some items in your cart changed. Please review it before checking out."))
        return redirect("cart:detail")

    user = request.user
    if request.method == "POST":
        form = CheckoutForm(request.POST, user=user)
        if form.is_valid():
            data = form.cleaned_data
            delivery = DeliveryDetails(**{name: (data.get(name) or "").strip() for name in ADDRESS_FIELDS})
            location = None
            if data["location"]:
                location = SharedLocation(
                    latitude=data["location"]["latitude"],
                    longitude=data["location"]["longitude"],
                    accuracy_m=data["location"]["accuracy"],
                )
            try:
                order = create_order_from_cart(
                    user=user,
                    cart=cart,
                    delivery=delivery,
                    phone=data["phone"],
                    customer_notes=data.get("customer_notes", ""),
                    location=location,
                    language=get_language() or "ar",
                    request=request,
                )
            except CheckoutError as error:
                messages.error(request, _checkout_error_message(error))
                return redirect("cart:detail")
            if data.get("save_address"):
                Address.objects.create(user=user, **{name: getattr(delivery, name) for name in ADDRESS_FIELDS})
            if not user.phone:
                user.phone = data["phone"]
                user.save(update_fields=["phone"])
            return redirect("orders:confirmation", pk=order.pk)
    else:
        default_address = Address.objects.filter(user=user, is_default=True).first()
        form = CheckoutForm(
            user=user,
            initial={"phone": user.phone, "saved_address": default_address.pk if default_address else None},
        )
    return render(request, "orders/checkout.html", {"form": form, "cart_view": cart_view})


def _customer_order(request, pk) -> Order:
    # Filtering by the logged-in customer means other users get a 404, never the order.
    return get_object_or_404(Order, pk=pk, customer=request.user)


@login_required
def confirmation(request, pk):
    order = _customer_order(request, pk)
    notification = get_notifier().new_order(order, request=request)
    return render(request, "orders/confirmation.html", {"order": order, "notification": notification})


@login_required
@require_POST
def whatsapp_opened(request, pk):
    """Record that the customer pressed the WhatsApp button (not that a message was sent)."""
    order = _customer_order(request, pk)
    record_whatsapp_opened(order)
    if request.headers.get("X-Requested-With") == "fetch":
        return HttpResponse(status=204)
    notification = get_notifier().new_order(order, request=request)
    if notification.action_url:
        return redirect(notification.action_url)
    return redirect("orders:confirmation", pk=order.pk)


@login_required
def order_list(request):
    orders = Order.objects.filter(customer=request.user).prefetch_related("items").order_by("-created_at")
    page = Paginator(orders, ORDERS_PAGE_SIZE).get_page(request.GET.get("page"))
    return render(request, "orders/order_list.html", {"page_obj": page, "orders": page.object_list})


@login_required
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related("items", "status_history"), pk=pk, customer=request.user)
    steps = []
    if order.status != OrderStatus.CANCELLED:
        reached = PROGRESS_STEPS.index(order.status) if order.status in PROGRESS_STEPS else 0
        steps = [
            {"value": value, "label": OrderStatus(value).label, "done": index <= reached, "current": index == reached}
            for index, value in enumerate(PROGRESS_STEPS)
        ]
    return render(request, "orders/order_detail.html", {"order": order, "steps": steps})
