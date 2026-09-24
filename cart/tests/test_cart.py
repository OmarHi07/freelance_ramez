import uuid

import pytest
from django.urls import reverse
from django.utils import translation

from cart.models import Cart, CartItem
from cart.services import SESSION_KEY
from conftest import PASSWORD, make_product

pytestmark = pytest.mark.django_db


def url(name, **kwargs):
    with translation.override("en"):
        return reverse(name, kwargs=kwargs or None)


def add(client, variant, quantity=1, **headers):
    return client.post(url("cart:add"), {"variant": variant.pk, "quantity": quantity}, headers=headers)


def test_anonymous_cart_add_update_remove(client, site_settings):
    product = make_product(price="25.00", stock=5)
    variant = product.variants.first()
    response = add(client, variant, 2)
    assert response.status_code == 302
    cart = Cart.objects.get(pk=client.session[SESSION_KEY])
    assert cart.user is None
    item = cart.items.get()
    assert item.quantity == 2

    page = client.get(url("cart:detail"))
    assert page.context["cart_view"].totals.subtotal == 50

    client.post(url("cart:update", item_id=item.pk), {"quantity": 4})
    item.refresh_from_db()
    assert item.quantity == 4
    client.post(url("cart:remove", item_id=item.pk))
    assert not CartItem.objects.filter(pk=item.pk).exists()


def test_quantity_is_capped_by_stock_and_line_limit(client, site_settings):
    variant = make_product(stock=3).variants.first()
    add(client, variant, 2)
    add(client, variant, 5)
    assert CartItem.objects.get(variant=variant).quantity == 3


def test_out_of_stock_and_inactive_items_cannot_be_added(client, site_settings):
    sold_out = make_product(stock=0).variants.first()
    hidden = make_product(is_active=False).variants.first()
    add(client, sold_out)
    add(client, hidden)
    assert CartItem.objects.count() == 0


def test_htmx_add_returns_toast_and_badge(client, site_settings):
    variant = make_product().variants.first()
    response = add(client, variant, 2, HX_Request="true")
    html = response.content.decode()
    assert response.status_code == 200
    assert "data-toast" in html
    assert 'id="cart-badge"' in html and 'hx-swap-oob="true"' in html
    assert ">2<" in html.replace(" ", "")


def test_tampered_session_cart_id_is_ignored(client, site_settings):
    session = client.session
    session[SESSION_KEY] = "not-a-uuid"
    session.save()
    assert client.get(url("cart:detail")).status_code == 200
    session = client.session
    session[SESSION_KEY] = str(uuid.uuid4())
    session.save()
    assert client.get(url("cart:detail")).status_code == 200


def test_anonymous_cart_cannot_reach_a_users_cart(client, customer, site_settings):
    user_cart = Cart.objects.create(user=customer)
    CartItem.objects.create(cart=user_cart, variant=make_product().variants.first(), quantity=1)
    session = client.session
    session[SESSION_KEY] = str(user_cart.pk)
    session.save()
    assert client.get(url("cart:detail")).context["cart_view"].is_empty


def test_anonymous_cart_merges_safely_on_login(client, customer, site_settings):
    shared = make_product(stock=4).variants.first()
    only_anonymous = make_product(stock=10).variants.first()
    sold_out_later = make_product(stock=5).variants.first()

    user_cart = Cart.objects.create(user=customer)
    CartItem.objects.create(cart=user_cart, variant=shared, quantity=3)

    add(client, shared, 3)
    add(client, only_anonymous, 2)
    add(client, sold_out_later, 1)
    anonymous_id = client.session[SESSION_KEY]
    sold_out_later.stock_quantity = 0
    sold_out_later.save()

    response = client.post(url("accounts:login"), {"username": customer.email.upper(), "password": PASSWORD})
    assert response.status_code == 302

    user_cart.refresh_from_db()
    quantities = {item.variant_id: item.quantity for item in user_cart.items.all()}
    assert quantities[shared.pk] == 4  # 3 + 3 capped at stock 4
    assert quantities[only_anonymous.pk] == 2
    assert sold_out_later.pk not in quantities
    assert not Cart.objects.filter(pk=anonymous_id).exists()
    assert SESSION_KEY not in client.session


def test_anonymous_cart_is_adopted_when_user_has_no_cart(client, customer, site_settings):
    variant = make_product().variants.first()
    add(client, variant, 2)
    cart_id = client.session[SESSION_KEY]
    client.post(url("accounts:login"), {"username": customer.email, "password": PASSWORD})
    cart = Cart.objects.get(pk=cart_id)
    assert cart.user == customer
    assert cart.items.get().quantity == 2
