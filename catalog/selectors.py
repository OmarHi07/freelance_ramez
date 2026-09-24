"""Read-side query helpers for the storefront (keeps views thin and queries efficient)."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Prefetch, QuerySet

from catalog.models import Brand, Category, Product, ProductImage, ProductVariant
from catalog.services.pricing import attach_quotes

SORT_NEWEST = "newest"
SORT_PRICE_ASC = "price_asc"
SORT_PRICE_DESC = "price_desc"

AVAILABILITY_IN_STOCK = "in_stock"
AVAILABILITY_OUT_OF_STOCK = "out_of_stock"


def active_brands() -> QuerySet[Brand]:
    return Brand.objects.filter(is_active=True).order_by("display_order", "name_en")


def active_categories() -> QuerySet[Category]:
    return Category.objects.filter(is_active=True).order_by("display_order", "name_en")


def storefront_products() -> QuerySet[Product]:
    """Active products of active brands with everything a product card needs."""
    return (
        Product.objects.filter(is_active=True, brand__is_active=True)
        .select_related("brand")
        .prefetch_related(
            Prefetch("categories", queryset=Category.objects.order_by("display_order", "name_en")),
            Prefetch("images", queryset=ProductImage.objects.order_by("-is_primary", "display_order", "id")),
            Prefetch(
                "variants", queryset=ProductVariant.objects.filter(is_active=True).order_by("display_order", "id")
            ),
        )
        .order_by("-created_at")
    )


def brand_categories(brand: Brand) -> QuerySet[Category]:
    return active_categories().filter(products__brand=brand, products__is_active=True).distinct()


def filter_brand_products(brand: Brand, filters: dict) -> list[Product]:
    """Apply brand-page filters and sorting.

    Price filters and price sorting use the *final* (discounted) price shown to
    customers, so they run in Python after quotes are attached. Per-brand
    catalogues are small, and results are paginated afterwards.
    """
    queryset = storefront_products().filter(brand=brand)
    category = filters.get("category")
    if category:
        queryset = queryset.filter(categories=category)
    verification = filters.get("verification")
    if verification:
        queryset = queryset.filter(verification_status=verification)
    products = list(queryset.distinct())
    attach_quotes(products)

    availability = filters.get("availability")
    if availability == AVAILABILITY_IN_STOCK:
        products = [product for product in products if product.is_in_stock]
    elif availability == AVAILABILITY_OUT_OF_STOCK:
        products = [product for product in products if not product.is_in_stock]

    min_price: Decimal | None = filters.get("min_price")
    max_price: Decimal | None = filters.get("max_price")
    if min_price is not None:
        products = [product for product in products if product.quote.final >= min_price]
    if max_price is not None:
        products = [product for product in products if product.quote.final <= max_price]

    sort = filters.get("sort") or SORT_NEWEST
    if sort == SORT_PRICE_ASC:
        products.sort(key=lambda product: (product.quote.final, -product.pk))
    elif sort == SORT_PRICE_DESC:
        products.sort(key=lambda product: (product.quote.final, product.pk), reverse=True)
    else:
        products.sort(key=lambda product: (product.created_at, product.pk), reverse=True)
    return products


def related_products(product: Product, limit: int = 4) -> list[Product]:
    related = list(storefront_products().filter(brand_id=product.brand_id).exclude(pk=product.pk)[:limit])
    attach_quotes(related)
    return related
