"""Owner product form: generated SKUs and the Standard/Custom option switch."""

import pytest
from django.urls import reverse
from django.utils import translation

from catalog.models import STANDARD_OPTION_NAME_AR, STANDARD_OPTION_NAME_EN, Product, ProductVariant
from catalog.skus import PRODUCT_SKU_PREFIX, VARIANT_SKU_PREFIX
from conftest import make_brand, make_category, make_product

pytestmark = pytest.mark.django_db


def url(name, **kwargs):
    with translation.override("en"):
        return reverse(f"dashboard:{name}", kwargs=kwargs or None)


def payload(brand, category, **overrides):
    """A create POST with no SKU fields at all."""
    data = {
        "brand": brand.pk,
        "categories": [category.pk],
        "name_ar": "سوار",
        "name_en": "Bracelet",
        "slug": "bracelet",
        "description_ar": "",
        "description_en": "",
        "regular_price": "59.00",
        "verification_status": "CONFIRMED",
        "is_active": "on",
        "variants-TOTAL_FORMS": "1",
        "variants-INITIAL_FORMS": "0",
        "variants-MIN_NUM_FORMS": "0",
        "variants-MAX_NUM_FORMS": "1000",
        "variants-0-option_mode": "standard",
        "variants-0-stock_quantity": "9",
        "variants-0-display_order": "0",
        "variants-0-is_active": "on",
        "images-TOTAL_FORMS": "0",
        "images-INITIAL_FORMS": "0",
        "images-MIN_NUM_FORMS": "0",
        "images-MAX_NUM_FORMS": "1000",
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Generated SKUs
# ---------------------------------------------------------------------------
def test_product_and_variant_are_created_without_submitting_any_sku(staff_client, site_settings):
    brand, category = make_brand(), make_category()
    response = staff_client.post(url("product_create"), payload(brand, category))
    assert response.status_code == 302, response.context and response.context["form"].errors

    product = Product.objects.get(slug="bracelet")
    variant = product.variants.get()
    assert product.sku.startswith(PRODUCT_SKU_PREFIX)
    assert variant.sku.startswith(VARIANT_SKU_PREFIX)
    assert product.sku != variant.sku


def test_a_forged_sku_in_the_post_is_ignored(staff_client, site_settings):
    """The server stays authoritative even when the browser sends extra fields."""
    brand, category = make_brand(), make_category()
    data = payload(brand, category, **{"sku": "HACKED-PRODUCT", "variants-0-sku": "HACKED-VARIANT"})
    assert staff_client.post(url("product_create"), data).status_code == 302

    product = Product.objects.get(slug="bracelet")
    assert product.sku != "HACKED-PRODUCT"
    assert product.sku.startswith(PRODUCT_SKU_PREFIX)
    variant = product.variants.get()
    assert variant.sku != "HACKED-VARIANT"
    assert variant.sku.startswith(VARIANT_SKU_PREFIX)


def test_editing_a_product_through_the_form_keeps_both_skus(staff_client, site_settings):
    brand, category = make_brand(), make_category()
    staff_client.post(url("product_create"), payload(brand, category))
    product = Product.objects.get(slug="bracelet")
    variant = product.variants.get()
    before = (product.sku, variant.sku)

    edit = payload(
        make_brand(),
        make_category(),
        **{
            "name_en": "Renamed bracelet",
            "name_ar": "سوار بعد التعديل",
            "slug": "renamed-bracelet",
            "variants-INITIAL_FORMS": "1",
            "variants-0-id": str(variant.pk),
            "variants-0-option_mode": "custom",
            "variants-0-name_ar": "فضي",
            "variants-0-name_en": "Silver",
            "variants-0-stock_quantity": "3",
            "sku": "SHOULD-BE-IGNORED",
            "variants-0-sku": "SHOULD-BE-IGNORED-TOO",
        },
    )
    assert staff_client.post(url("product_update", pk=product.pk), edit).status_code == 302

    product.refresh_from_db()
    variant.refresh_from_db()
    assert (product.sku, variant.sku) == before
    assert product.slug == "renamed-bracelet" and variant.name_en == "Silver"


@pytest.mark.parametrize("page", ["create", "update"])
def test_owner_form_html_has_no_editable_sku_input(staff_client, site_settings, page):
    target = url("product_create") if page == "create" else url("product_update", pk=make_product().pk)
    html = staff_client.get(target).content.decode()
    assert 'name="sku"' not in html
    assert "-sku" not in html.replace("data-", "")


# ---------------------------------------------------------------------------
# Standard / custom option modes
# ---------------------------------------------------------------------------
def test_standard_mode_stores_both_localized_names_without_posted_names(staff_client, site_settings):
    brand, category = make_brand(), make_category()
    data = payload(brand, category)
    assert "variants-0-name_ar" not in data and "variants-0-name_en" not in data

    assert staff_client.post(url("product_create"), data).status_code == 302
    variant = Product.objects.get(slug="bracelet").variants.get()
    assert variant.name_ar == STANDARD_OPTION_NAME_AR
    assert variant.name_en == STANDARD_OPTION_NAME_EN
    assert variant.stock_quantity == 9


def test_standard_mode_saves_even_when_nothing_at_all_is_typed(staff_client, site_settings):
    """The first row of a new product is mandatory, so a bare Standard pick still saves."""
    brand, category = make_brand(), make_category()
    data = payload(brand, category, **{"variants-0-stock_quantity": "0"})
    assert staff_client.post(url("product_create"), data).status_code == 302
    variant = Product.objects.get(slug="bracelet").variants.get()
    assert (variant.name_ar, variant.name_en) == (STANDARD_OPTION_NAME_AR, STANDARD_OPTION_NAME_EN)
    assert variant.stock_quantity == 0


def test_standard_mode_ignores_names_smuggled_into_the_post(staff_client, site_settings):
    brand, category = make_brand(), make_category()
    data = payload(brand, category, **{"variants-0-name_ar": "مزيف", "variants-0-name_en": "Forged"})
    assert staff_client.post(url("product_create"), data).status_code == 302
    variant = Product.objects.get(slug="bracelet").variants.get()
    assert (variant.name_ar, variant.name_en) == (STANDARD_OPTION_NAME_AR, STANDARD_OPTION_NAME_EN)


@pytest.mark.parametrize(
    ("missing", "expected_error_field"),
    [("variants-0-name_ar", "name_ar"), ("variants-0-name_en", "name_en")],
)
def test_custom_mode_requires_both_names(staff_client, site_settings, missing, expected_error_field):
    brand, category = make_brand(), make_category()
    data = payload(
        brand,
        category,
        **{
            "variants-0-option_mode": "custom",
            "variants-0-name_ar": "ذهبي",
            "variants-0-name_en": "Gold",
        },
    )
    data[missing] = ""
    response = staff_client.post(url("product_create"), data)
    assert response.status_code == 200
    assert expected_error_field in response.context["variant_formset"].forms[0].errors
    assert not Product.objects.filter(slug="bracelet").exists()


def test_a_missing_or_unknown_option_mode_falls_back_to_custom(staff_client, site_settings):
    """A forged POST cannot skip validation by dropping the mode field."""
    brand, category = make_brand(), make_category()
    for mode in ("", "not-a-real-mode"):
        data = payload(brand, category, **{"variants-0-option_mode": mode})
        response = staff_client.post(url("product_create"), data)
        assert response.status_code == 200, mode
        errors = response.context["variant_formset"].forms[0].errors
        assert "name_ar" in errors and "name_en" in errors, mode
        assert not Product.objects.filter(slug="bracelet").exists()


def test_existing_standard_variant_opens_in_standard_mode(staff_client, site_settings):
    product = make_product(variants=0)
    ProductVariant.objects.create(
        product=product, name_ar=STANDARD_OPTION_NAME_AR, name_en=STANDARD_OPTION_NAME_EN, stock_quantity=4
    )
    formset = staff_client.get(url("product_update", pk=product.pk)).context["variant_formset"]
    assert formset.forms[0]["option_mode"].value() == "standard"


def test_existing_custom_variant_stays_custom(staff_client, site_settings):
    product = make_product(variants=0)
    ProductVariant.objects.create(product=product, name_ar="ذهبي", name_en="Gold", stock_quantity=4)
    formset = staff_client.get(url("product_update", pk=product.pk)).context["variant_formset"]
    assert formset.forms[0]["option_mode"].value() == "custom"


def test_editing_an_existing_standard_variant_keeps_its_names(staff_client, site_settings):
    brand, category = make_brand(), make_category()
    staff_client.post(url("product_create"), payload(brand, category))
    product = Product.objects.get(slug="bracelet")
    variant = product.variants.get()

    edit = payload(
        brand,
        category,
        **{
            "variants-INITIAL_FORMS": "1",
            "variants-0-id": str(variant.pk),
            "variants-0-option_mode": "standard",
            "variants-0-stock_quantity": "25",
        },
    )
    assert staff_client.post(url("product_update", pk=product.pk), edit).status_code == 302
    variant.refresh_from_db()
    assert (variant.name_ar, variant.name_en) == (STANDARD_OPTION_NAME_AR, STANDARD_OPTION_NAME_EN)
    assert variant.stock_quantity == 25


def test_editing_an_existing_custom_variant_and_switching_to_standard(staff_client, site_settings):
    product = make_product(variants=0)
    variant = ProductVariant.objects.create(
        product=product, name_ar="ذهبي", name_en="Gold", stock_quantity=4, color_hex="#C9A85C"
    )
    brand, category = product.brand, make_category()
    edit = payload(
        brand,
        category,
        **{
            "name_ar": product.name_ar,
            "name_en": product.name_en,
            "slug": product.slug,
            "regular_price": str(product.regular_price),
            "variants-INITIAL_FORMS": "1",
            "variants-0-id": str(variant.pk),
            "variants-0-option_mode": "standard",
            "variants-0-stock_quantity": "6",
        },
    )
    assert staff_client.post(url("product_update", pk=product.pk), edit).status_code == 302
    variant.refresh_from_db()
    assert (variant.name_ar, variant.name_en) == (STANDARD_OPTION_NAME_AR, STANDARD_OPTION_NAME_EN)
    assert variant.stock_quantity == 6


def test_a_dynamically_added_row_is_validated_on_the_server(staff_client, site_settings):
    """Rows added with "Add another option" go through the same validation."""
    brand, category = make_brand(), make_category()
    staff_client.post(url("product_create"), payload(brand, category))
    product = Product.objects.get(slug="bracelet")
    first = product.variants.get()

    base = {
        "variants-TOTAL_FORMS": "2",
        "variants-INITIAL_FORMS": "1",
        "variants-0-id": str(first.pk),
        "variants-0-option_mode": "standard",
        "variants-0-stock_quantity": "9",
        "variants-1-display_order": "1",
        "variants-1-is_active": "on",
        "variants-1-stock_quantity": "5",
    }

    # A custom row added without names is rejected.
    bad = payload(brand, category, **base, **{"variants-1-option_mode": "custom"})
    response = staff_client.post(url("product_update", pk=product.pk), bad)
    assert response.status_code == 200
    assert "name_ar" in response.context["variant_formset"].forms[1].errors
    assert product.variants.count() == 1

    # The same row with both names is accepted.
    good = payload(
        brand,
        category,
        **base,
        **{"variants-1-option_mode": "custom", "variants-1-name_ar": "فضي", "variants-1-name_en": "Silver"},
    )
    assert staff_client.post(url("product_update", pk=product.pk), good).status_code == 302
    assert product.variants.count() == 2
    added = product.variants.get(name_en="Silver")
    assert added.sku.startswith(VARIANT_SKU_PREFIX) and added.stock_quantity == 5


def test_a_product_still_needs_at_least_one_active_option(staff_client, site_settings):
    brand, category = make_brand(), make_category()
    data = payload(brand, category)
    data.pop("variants-0-is_active")
    response = staff_client.post(url("product_create"), data)
    assert response.status_code == 200
    assert response.context["variant_formset"].non_form_errors()
    assert not Product.objects.filter(slug="bracelet").exists()
