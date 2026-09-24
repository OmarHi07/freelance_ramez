"""Root URL configuration.

Customer- and owner-facing pages live under ``/ar/`` and ``/en/`` via
``i18n_patterns``. Unprefixed URLs such as ``/owner/`` are redirected by
LocaleMiddleware to the visitor's language. Technical endpoints are unprefixed.
"""

import re

from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.i18n import set_language
from django.views.static import serve as serve_media

from core import views as core_views
from core.constants import BUSINESS_NAME

admin.site.site_header = f"{BUSINESS_NAME} · Technical admin"
admin.site.site_title = f"{BUSINESS_NAME} admin"
admin.site.index_title = "Technical fallback — use /owner/ for day-to-day work"

urlpatterns = [
    path("healthz/", core_views.healthz, name="healthz"),
    path("robots.txt", core_views.robots_txt, name="robots_txt"),
    path("i18n/setlang/", set_language, name="set_language"),
    path("django-admin/", admin.site.urls),
]

urlpatterns += i18n_patterns(
    path("", include("core.urls")),
    path("", include("catalog.urls")),
    path("cart/", include("cart.urls")),
    path("account/", include("accounts.urls")),
    path("orders/", include("orders.urls")),
    path("owner/", include("dashboard.urls")),
    prefix_default_language=True,
)

# Local media files are served by Django only in development, or when explicitly enabled
# (e.g. a small staging server with a persistent volume). Use S3/Cloudinary in production.
if settings.MEDIA_STORAGE_BACKEND == "local" and (settings.DEBUG or settings.SERVE_MEDIA_FILES):
    media_prefix = re.escape(settings.MEDIA_URL.lstrip("/"))
    urlpatterns += [
        re_path(rf"^{media_prefix}(?P<path>.*)$", serve_media, {"document_root": settings.MEDIA_ROOT}),
    ]
