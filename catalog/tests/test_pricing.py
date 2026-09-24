from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from catalog.models import DiscountType, Promotion, PromotionScope
from catalog.services.pricing import discount_amount, price_lines, quote_price, quote_variant
from conftest import make_brand, make_category, make_product, make_promotion

pytestmark = pytest.mark.django_db


def test_percentage_discount_is_rounded_half_up():
    product = make_product(price="59.90")
    make_promotion(value="20.00")
    quote = quote_price(product, product.regular_price)
    assert quote.discount == Decimal("11.98")
    assert quote.final == Decimal("47.92")
    assert quote.percent_off == 20


def test_fixed_discount_never_makes_price_negative():
    product = make_product(price="15.00")
    promo = make_promotion(discount_type=DiscountType.FIXED, value="40.00")
    assert discount_amount(promo, Decimal("15.00")) == Decimal("15.00")
    assert quote_price(product, product.regular_price).final == Decimal("0.00")


@pytest.mark.parametrize(
    ("starts", "ends", "enabled", "applies"),
    [
        (-1, 1, True, True),  # running
        (1, 5, True, False),  # not started yet
        (-5, -1, True, False),  # already ended
        (-1, 1, False, False),  # disabled
        (-1, None, True, True),  # no end date
    ],
)
def test_promotion_date_and_enabled_rules(starts, ends, enabled, applies):
    product = make_product(price="100.00")
    make_promotion(value="10.00", starts=starts, ends=ends, is_enabled=enabled)
    quote = quote_price(product, product.regular_price)
    assert quote.has_discount is applies


def test_end_time_is_exclusive():
    product = make_product(price="100.00")
    promo = make_promotion(value="10.00")
    assert quote_price(product, product.regular_price, now=promo.ends_at).has_discount is False
    assert quote_price(product, product.regular_price, now=promo.ends_at - timedelta(seconds=1)).has_discount


def test_scope_rules_brand_category_product():
    brand, other_brand = make_brand(), make_brand()
    category = make_category()
    in_brand = make_product(brand, price="100.00")
    in_category = make_product(other_brand, price="100.00", categories=[category])
    specific = make_product(other_brand, price="100.00")
    unrelated = make_product(other_brand, price="100.00")
    make_promotion(scope=PromotionScope.BRAND, brand=brand, value="10.00")
    make_promotion(scope=PromotionScope.CATEGORY, category=category, value="20.00")
    make_promotion(scope=PromotionScope.PRODUCT, product=specific, value="30.00")

    assert quote_price(in_brand, Decimal("100.00")).discount == Decimal("10.00")
    assert quote_price(in_category, Decimal("100.00")).discount == Decimal("20.00")
    assert quote_price(specific, Decimal("100.00")).discount == Decimal("30.00")
    assert quote_price(unrelated, Decimal("100.00")).has_discount is False


def test_best_discount_wins_and_discounts_never_stack():
    brand = make_brand()
    product = make_product(brand, price="100.00")
    make_promotion(value="10.00")  # store 10%  -> 10.00
    best = make_promotion(scope=PromotionScope.BRAND, brand=brand, discount_type=DiscountType.FIXED, value="15.00")
    make_promotion(scope=PromotionScope.PRODUCT, product=product, value="12.00")  # 12.00
    quote = quote_price(product, product.regular_price)
    assert quote.promotion == best
    assert quote.discount == Decimal("15.00")  # not 10 + 15 + 12
    assert quote.final == Decimal("85.00")


def test_higher_priority_overrides_bigger_discount():
    product = make_product(price="100.00")
    make_promotion(value="50.00", priority=0)
    preferred = make_promotion(value="5.00", priority=10)
    quote = quote_price(product, product.regular_price)
    assert quote.promotion == preferred
    assert quote.discount == Decimal("5.00")


def test_variant_price_override_is_discounted():
    product = make_product(price="100.00")
    variant = product.variants.first()
    variant.price_override = Decimal("80.00")
    variant.save()
    make_promotion(value="25.00")
    quote = quote_variant(variant)
    assert quote.original == Decimal("80.00")
    assert quote.final == Decimal("60.00")


def test_price_lines_total_is_products_only(site_settings):
    product = make_product(price="30.00")
    variant = product.variants.first()
    make_promotion(value="10.00")
    totals = price_lines([(variant, 3)], site_settings)
    assert totals.subtotal == Decimal("90.00")
    assert totals.discount_total == Decimal("9.00")
    assert totals.total == Decimal("81.00")  # subtotal minus discounts
    assert totals.items_total == totals.total


def test_no_delivery_fee_is_added_even_if_old_settings_still_store_one(site_settings):
    """Delivery is agreed on WhatsApp, so a stale stored fee must not resurface."""
    variant = make_product(price="30.00").variants.first()
    site_settings.default_delivery_fee = Decimal("20.00")
    site_settings.free_delivery_threshold = Decimal("500.00")
    totals = price_lines([(variant, 1)], site_settings)
    assert totals.delivery_fee == Decimal("0.00")
    assert totals.total == Decimal("30.00")


def test_promotion_validation_rules():
    product = make_product(price="20.00")
    now = timezone.now()
    too_big = Promotion(
        name_en="x",
        name_ar="x",
        discount_type=DiscountType.PERCENTAGE,
        value=Decimal("120"),
        scope=PromotionScope.STORE,
        starts_at=now,
    )
    with pytest.raises(ValidationError) as exc:
        too_big.full_clean()
    assert "value" in exc.value.message_dict

    fixed_over_price = Promotion(
        name_en="x",
        name_ar="x",
        discount_type=DiscountType.FIXED,
        value=Decimal("25"),
        scope=PromotionScope.PRODUCT,
        product=product,
        starts_at=now,
    )
    with pytest.raises(ValidationError) as exc:
        fixed_over_price.full_clean()
    assert "value" in exc.value.message_dict

    bad_dates = Promotion(
        name_en="x",
        name_ar="x",
        discount_type=DiscountType.PERCENTAGE,
        value=Decimal("5"),
        scope=PromotionScope.STORE,
        starts_at=now,
        ends_at=now - timedelta(days=1),
    )
    with pytest.raises(ValidationError) as exc:
        bad_dates.full_clean()
    assert "ends_at" in exc.value.message_dict

    missing_target = Promotion(
        name_en="x",
        name_ar="x",
        discount_type=DiscountType.PERCENTAGE,
        value=Decimal("5"),
        scope=PromotionScope.BRAND,
        starts_at=now,
    )
    with pytest.raises(ValidationError) as exc:
        missing_target.full_clean()
    assert "brand" in exc.value.message_dict


def test_database_rejects_percentage_over_100():
    with pytest.raises(IntegrityError), transaction.atomic():
        Promotion.objects.create(
            name_en="x",
            name_ar="x",
            discount_type=DiscountType.PERCENTAGE,
            value=Decimal("150"),
            scope=PromotionScope.STORE,
            starts_at=timezone.now(),
        )
