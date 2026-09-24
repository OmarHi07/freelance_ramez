from __future__ import annotations

from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from catalog import selectors
from catalog.forms import BrandProductFilterForm
from catalog.models import Brand
from catalog.services.pricing import attach_quotes

BRAND_PAGE_SIZE = 12


def brand_list(request):
    return render(request, "catalog/brand_list.html", {"brands": selectors.active_brands()})


def brand_detail(request, slug: str):
    brand = get_object_or_404(Brand, slug=slug, is_active=True)
    form = BrandProductFilterForm(request.GET or None, brand=brand)
    filters = form.cleaned_data if form.is_bound and form.is_valid() else {}
    products = selectors.filter_brand_products(brand, filters)
    page = Paginator(products, BRAND_PAGE_SIZE).get_page(request.GET.get("page"))
    context = {
        "brand": brand,
        "form": form,
        "page_obj": page,
        "products": page.object_list,
        "result_count": len(products),
    }
    if request.headers.get("HX-Request") and request.headers.get("HX-Target") == "product-results":
        return render(request, "catalog/partials/product_results.html", context)
    return render(request, "catalog/brand_detail.html", context)


def product_detail(request, slug: str):
    product = get_object_or_404(selectors.storefront_products(), slug=slug)
    attach_quotes([product])
    variants = product.active_variants
    selected = next((variant for variant in variants if variant.is_available), variants[0] if variants else None)
    context = {
        "product": product,
        "brand": product.brand,
        "variants": variants,
        "selected_variant": selected,
        "images": product.sorted_images,
        "related_products": selectors.related_products(product),
        "max_quantity": _max_quantity(selected),
    }
    return render(request, "catalog/product_detail.html", context)


def _max_quantity(variant) -> int:
    from django.conf import settings

    if variant is None:
        return 1
    return max(1, min(settings.MAX_CART_LINE_QUANTITY, variant.stock_quantity))
