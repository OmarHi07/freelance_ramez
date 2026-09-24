from __future__ import annotations

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from catalog import selectors
from catalog.services.pricing import attach_quotes
from core.middleware import health_response


def home(request):
    brands = selectors.active_brands()
    featured = list(selectors.storefront_products().filter(is_featured=True)[:8])
    new_arrivals = list(selectors.storefront_products().order_by("-created_at")[:8])
    attach_quotes(featured + new_arrivals)
    return render(
        request,
        "core/home.html",
        {"brands": brands, "featured_products": featured, "new_arrivals": new_arrivals},
    )


@never_cache
@require_GET
def healthz(request):
    """Liveness/readiness probe (normally answered earlier by HealthCheckMiddleware)."""
    return health_response()


@require_GET
def robots_txt(request):
    lines = [
        "User-agent: *",
        "Disallow: /owner/",
        "Disallow: /ar/owner/",
        "Disallow: /en/owner/",
        "Disallow: /django-admin/",
        "Disallow: /ar/account/",
        "Disallow: /en/account/",
        "Disallow: /ar/cart/",
        "Disallow: /en/cart/",
        "Disallow: /ar/orders/",
        "Disallow: /en/orders/",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


def csrf_failure(request, reason: str = ""):
    return render(request, "errors/csrf.html", status=403)
