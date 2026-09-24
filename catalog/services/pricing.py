"""Discount calculation service.

Rules
-----
* Only promotions that are enabled and inside their start/end window apply.
* A promotion matches an item by scope: entire store, brand, category or product.
* Exactly one promotion applies per item (discounts never stack).
* Among matching promotions the one with the highest ``priority`` wins. When
  priorities are equal, the biggest discount for that item wins. Remaining ties
  go to the most specific scope (product > category > brand > store), then to
  the oldest promotion, so the result is deterministic.
* Percentage discounts are 0-100 %; fixed discounts are capped at the item
  price, so a final price can never be negative.
* All amounts are ``Decimal`` rounded half-up to 0.01. Floats are never used.
* No delivery fee is ever added: the owner agrees it with the customer on
  WhatsApp after the order is placed.

The same functions are used to display prices and, on the server, to create
orders, so totals submitted by a browser are never trusted.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from catalog.models import DiscountType, Product, ProductVariant, Promotion, PromotionScope
from core.constants import MONEY_QUANTUM

ZERO = Decimal("0.00")
HUNDRED = Decimal("100")

SCOPE_SPECIFICITY = {
    PromotionScope.PRODUCT: 3,
    PromotionScope.CATEGORY: 2,
    PromotionScope.BRAND: 1,
    PromotionScope.STORE: 0,
}


def money(value) -> Decimal:
    return Decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PriceQuote:
    original: Decimal
    discount: Decimal = ZERO
    promotion: Promotion | None = None

    @property
    def final(self) -> Decimal:
        return money(self.original - self.discount)

    @property
    def has_discount(self) -> bool:
        return self.discount > ZERO

    @property
    def percent_off(self) -> int:
        if not self.has_discount or self.original <= ZERO:
            return 0
        return int((self.discount / self.original * HUNDRED).to_integral_value(rounding=ROUND_HALF_UP))


def load_active_promotions(now=None) -> list[Promotion]:
    """Fetch the (small) set of currently active promotions once per request."""
    return list(Promotion.objects.active(now))


def _category_ids(product: Product) -> set[int]:
    # Uses the prefetch cache when the caller prefetched categories.
    return {category.pk for category in product.categories.all()}


def promotion_applies(promotion: Promotion, product: Product, category_ids: set[int] | None = None) -> bool:
    if promotion.scope == PromotionScope.STORE:
        return True
    if promotion.scope == PromotionScope.BRAND:
        return promotion.brand_id == product.brand_id
    if promotion.scope == PromotionScope.PRODUCT:
        return promotion.product_id == product.pk
    if promotion.scope == PromotionScope.CATEGORY:
        if category_ids is None:
            category_ids = _category_ids(product)
        return promotion.category_id in category_ids
    return False


def discount_amount(promotion: Promotion, base_price: Decimal) -> Decimal:
    """Per-unit discount, clamped to ``[0, base_price]``."""
    base_price = money(base_price)
    if promotion.discount_type == DiscountType.PERCENTAGE:
        percent = min(max(Decimal(promotion.value), ZERO), HUNDRED)
        amount = money(base_price * percent / HUNDRED)
    else:
        amount = money(max(Decimal(promotion.value), ZERO))
    return min(amount, base_price)


def select_promotion(
    product: Product,
    base_price: Decimal,
    promotions: Iterable[Promotion],
    *,
    now=None,
    category_ids: set[int] | None = None,
) -> tuple[Promotion | None, Decimal]:
    now = now or timezone.now()
    best: tuple[tuple, Promotion, Decimal] | None = None
    for promotion in promotions:
        if not promotion.is_active_at(now):
            continue
        if promotion.scope == PromotionScope.CATEGORY and category_ids is None:
            category_ids = _category_ids(product)
        if not promotion_applies(promotion, product, category_ids):
            continue
        amount = discount_amount(promotion, base_price)
        if amount <= ZERO:
            continue
        rank = (
            promotion.priority,
            amount,
            SCOPE_SPECIFICITY.get(promotion.scope, 0),
            -(promotion.pk or 0),
        )
        if best is None or rank > best[0]:
            best = (rank, promotion, amount)
    if best is None:
        return None, ZERO
    return best[1], best[2]


def quote_price(product: Product, base_price: Decimal, promotions=None, *, now=None) -> PriceQuote:
    if promotions is None:
        promotions = load_active_promotions(now)
    promotion, amount = select_promotion(product, base_price, promotions, now=now)
    return PriceQuote(original=money(base_price), discount=amount, promotion=promotion)


def quote_variant(variant: ProductVariant, promotions=None, *, now=None) -> PriceQuote:
    return quote_price(variant.product, variant.base_price, promotions, now=now)


def attach_quotes(products: Sequence[Product], promotions=None, *, now=None) -> Sequence[Product]:
    """Annotate products (and their active variants) with ``quote`` attributes.

    ``product.quote`` is the lowest final price among active variants (or the
    regular price when the product has no active variant) and
    ``product.price_varies`` tells templates to show "from".
    """
    if promotions is None:
        promotions = load_active_promotions(now)
    for product in products:
        variants = product.active_variants
        quotes = []
        for variant in variants:
            variant.quote = quote_price(product, variant.base_price, promotions, now=now)
            quotes.append(variant.quote)
        if quotes:
            product.quote = min(quotes, key=lambda quote: (quote.final, quote.original))
            product.price_varies = len({quote.final for quote in quotes}) > 1
        else:
            product.quote = quote_price(product, product.regular_price, promotions, now=now)
            product.price_varies = False
    return products


# ---------------------------------------------------------------------------
# Order / cart totals
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PricedLine:
    variant: ProductVariant
    quantity: int
    quote: PriceQuote

    @property
    def original_total(self) -> Decimal:
        return money(self.quote.original * self.quantity)

    @property
    def discount_total(self) -> Decimal:
        return money(self.quote.discount * self.quantity)

    @property
    def line_total(self) -> Decimal:
        return money(self.quote.final * self.quantity)


@dataclass(frozen=True)
class Totals:
    """Checkout totals. Delivery is never part of them.

    The owner agrees the delivery cost with each customer on WhatsApp after the
    order, so ``total`` is exactly the products total: subtotal minus discounts.
    ``delivery_fee`` stays at zero and is kept only so the field lines up with
    the historical ``Order.delivery_fee`` snapshot.
    """

    lines: list[PricedLine] = field(default_factory=list)
    subtotal: Decimal = ZERO  # before discounts
    discount_total: Decimal = ZERO
    delivery_fee: Decimal = ZERO
    total: Decimal = ZERO

    @property
    def items_total(self) -> Decimal:
        return money(self.subtotal - self.discount_total)

    @property
    def item_count(self) -> int:
        return sum(line.quantity for line in self.lines)


def price_lines(
    items: Iterable[tuple[ProductVariant, int]], site_settings=None, promotions=None, *, now=None
) -> Totals:
    """Compute authoritative totals for ``(variant, quantity)`` pairs.

    ``site_settings`` is accepted for call-site compatibility and deliberately
    ignored: no delivery fee is added even if an old row still stores one.
    """
    if promotions is None:
        promotions = load_active_promotions(now)
    lines = [
        PricedLine(variant=variant, quantity=quantity, quote=quote_variant(variant, promotions, now=now))
        for variant, quantity in items
    ]
    subtotal = money(sum((line.original_total for line in lines), ZERO))
    discount_total = money(sum((line.discount_total for line in lines), ZERO))
    return Totals(
        lines=lines,
        subtotal=subtotal,
        discount_total=discount_total,
        delivery_fee=ZERO,
        total=money(subtotal - discount_total),
    )
