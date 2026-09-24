from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import translation

from catalog.models import Brand, VerificationStatus
from conftest import make_brand, make_category, make_product, make_promotion

pytestmark = pytest.mark.django_db


def url(name, lang="en", **kwargs):
    with translation.override(lang):
        return reverse(name, kwargs=kwargs or None)


@pytest.mark.parametrize("lang", ["ar", "en"])
def test_anonymous_visitor_can_browse(client, site_settings, lang):
    brand = make_brand()
    product = make_product(brand)
    for target in (
        url("core:home", lang),
        url("catalog:brand_list", lang),
        url("catalog:brand_detail", lang, slug=brand.slug),
        url("catalog:product_detail", lang, slug=product.slug),
    ):
        response = client.get(target)
        assert response.status_code == 200, target
    response = client.get(url("catalog:product_detail", lang, slug=product.slug))
    assert product.localized("name") in response.content.decode() or product.name_en in response.content.decode()


def test_inactive_brand_and_product_are_hidden(client, site_settings):
    hidden_brand = make_brand(is_active=False)
    product_of_hidden = make_product(hidden_brand)
    hidden_product = make_product(is_active=False)
    assert client.get(url("catalog:brand_detail", slug=hidden_brand.slug)).status_code == 404
    assert client.get(url("catalog:product_detail", slug=product_of_hidden.slug)).status_code == 404
    assert client.get(url("catalog:product_detail", slug=hidden_product.slug)).status_code == 404


def test_product_page_shows_badge_prices_and_related(client, site_settings):
    brand = make_brand()
    product = make_product(brand, price="80.00", verification_status=VerificationStatus.NOT_CONFIRMED)
    related = make_product(brand)
    make_promotion(value="25.00")
    html = client.get(url("catalog:product_detail", slug=product.slug)).content.decode()
    assert "Not confirmed by brand" in html
    assert "₪60.00" in html and "₪80.00" in html  # final and struck-through original
    assert related.name_en in html


def test_brand_page_filters_and_sorting(client, site_settings):
    brand = make_brand()
    earrings = make_category(slug="earrings")
    cheap = make_product(brand, price="20.00", categories=[earrings])
    expensive = make_product(brand, price="90.00", verification_status=VerificationStatus.UNKNOWN)
    sold_out = make_product(brand, price="50.00", stock=0)
    base = url("catalog:brand_detail", slug=brand.slug)

    page = client.get(base, {"sort": "price_asc"}).context["products"]
    assert [p.pk for p in page] == [cheap.pk, sold_out.pk, expensive.pk]
    page = client.get(base, {"sort": "price_desc"}).context["products"]
    assert [p.pk for p in page][0] == expensive.pk
    assert [p.pk for p in client.get(base, {"category": "earrings"}).context["products"]] == [cheap.pk]
    in_stock = {p.pk for p in client.get(base, {"availability": "in_stock"}).context["products"]}
    assert sold_out.pk not in in_stock and cheap.pk in in_stock
    unknown = [p.pk for p in client.get(base, {"verification": "UNKNOWN"}).context["products"]]
    assert unknown == [expensive.pk]
    priced = [p.pk for p in client.get(base, {"min_price": "30", "max_price": "60"}).context["products"]]
    assert priced == [sold_out.pk]


def test_price_filter_uses_discounted_price(client, site_settings):
    brand = make_brand()
    product = make_product(brand, price="100.00")
    make_promotion(value="50.00")
    base = url("catalog:brand_detail", slug=brand.slug)
    assert [p.pk for p in client.get(base, {"max_price": "60"}).context["products"]] == [product.pk]


def test_htmx_filter_returns_partial(client, site_settings):
    brand = make_brand()
    make_product(brand)
    response = client.get(
        url("catalog:brand_detail", slug=brand.slug), headers={"HX-Request": "true", "HX-Target": "product-results"}
    )
    html = response.content.decode()
    assert 'id="product-results"' in html
    assert "<html" not in html


def test_brand_colours_are_validated():
    brand = Brand(name_en="X", name_ar="X", slug="x", primary_color="red; background:url(x)", secondary_color="#000")
    with pytest.raises(ValidationError) as exc:
        brand.full_clean()
    assert "primary_color" in exc.value.message_dict
    assert "secondary_color" in exc.value.message_dict  # #000 is not six digits


def test_database_rejects_invalid_colour_and_save_sanitizes():
    brand = make_brand()
    with pytest.raises(IntegrityError), transaction.atomic():
        Brand.objects.filter(pk=brand.pk).update(primary_color="#ZZZZZZ")
    brand.primary_color = "</style><script>"
    brand.save()  # model save falls back to a safe default instead of storing CSS
    brand.refresh_from_db()
    assert brand.primary_color == "#F8C8DC"


def test_brand_text_colour_keeps_contrast():
    dark = make_brand(primary_color="#1A1A1A")
    light = make_brand(primary_color="#FFF8FA")
    assert dark.text_on_primary == "#FFFFFF"
    assert light.text_on_primary == "#251D21"


def test_pagination_on_brand_page(client, site_settings):
    brand = make_brand()
    for _ in range(14):
        make_product(brand)
    base = url("catalog:brand_detail", slug=brand.slug)
    assert len(client.get(base).context["products"]) == 12
    assert len(client.get(base, {"page": 2}).context["products"]) == 2


def test_query_count_is_bounded_on_brand_page(client, site_settings, django_assert_max_num_queries):
    brand = make_brand()
    for _ in range(10):
        make_product(brand, variants=2)
    with django_assert_max_num_queries(20):
        client.get(url("catalog:brand_detail", slug=brand.slug))


def test_money_is_decimal_not_float():
    product = make_product(price="19.99")
    product.refresh_from_db()
    assert isinstance(product.regular_price, Decimal)
