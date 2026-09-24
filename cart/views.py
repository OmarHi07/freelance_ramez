from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from cart import services
from cart.forms import AddToCartForm, UpdateCartItemForm
from core.security import safe_next_url

ERROR_MESSAGES = {
    "unavailable": lambda: _("Sorry, this item is no longer available."),
    "out_of_stock": lambda: _("Sorry, this item is out of stock."),
    "missing": lambda: _("That item is no longer in your cart."),
}


def _error_text(code: str) -> str:
    return ERROR_MESSAGES.get(code, lambda: _("Something went wrong. Please try again."))()


def _is_htmx(request) -> bool:
    return request.headers.get("HX-Request") == "true"


@require_GET
def cart_detail(request):
    cart = services.get_cart(request)
    if cart is not None:
        for name in services.normalize_cart(cart):
            messages.info(request, _("We adjusted the quantity of “%(name)s” to the available stock.") % {"name": name})
    return render(request, "cart/cart_detail.html", {"cart_view": services.build_cart_view(request, cart)})


@require_POST
def cart_add(request):
    form = AddToCartForm(request.POST)
    next_url = safe_next_url(request, reverse("cart:detail"))
    if not form.is_valid():
        text = _("Please choose a valid option and quantity.")
        if _is_htmx(request):
            return render(request, "cart/partials/toast.html", {"level": "error", "text": text}, status=200)
        messages.error(request, text)
        return redirect(next_url)
    try:
        cart = services.get_cart(request, create=True)
        item = services.add_item(cart, form.cleaned_data["variant"], form.cleaned_data["quantity"])
    except services.CartError as exc:
        text = _error_text(str(exc))
        if _is_htmx(request):
            return render(request, "cart/partials/toast.html", {"level": "error", "text": text})
        messages.error(request, text)
        return redirect(next_url)
    text = _("Added to your cart: %(name)s") % {"name": item.variant.product.name}
    if _is_htmx(request):
        return render(
            request,
            "cart/partials/toast.html",
            {"level": "success", "text": text, "show_cart_link": True, "refresh_badge": True},
        )
    messages.success(request, text)
    return redirect(next_url)


@require_POST
def cart_update(request, item_id: int):
    cart = services.get_cart(request)
    form = UpdateCartItemForm(request.POST)
    if cart is not None and form.is_valid():
        try:
            services.set_quantity(cart, item_id, form.cleaned_data["quantity"])
        except services.CartError as exc:
            messages.error(request, _error_text(str(exc)))
    else:
        messages.error(request, _("Please enter a valid quantity."))
    return _cart_response(request)


@require_POST
def cart_remove(request, item_id: int):
    cart = services.get_cart(request)
    if cart is not None:
        services.remove_item(cart, item_id)
        messages.success(request, _("The item was removed from your cart."))
    return _cart_response(request)


def _cart_response(request):
    if _is_htmx(request):
        request._rawnaq_cart_count = None
        return render(
            request,
            "cart/partials/cart_body.html",
            {"cart_view": services.build_cart_view(request), "refresh_badge": True},
        )
    return redirect("cart:detail")
