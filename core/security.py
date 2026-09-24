"""Security helpers used by settings (django-axes) and views."""

from __future__ import annotations

from django.conf import settings
from django.utils.http import url_has_allowed_host_and_scheme


def get_client_ip(request) -> str | None:
    """Return the client IP without trusting spoofable headers.

    ``X-Forwarded-For`` is only used when ``TRUSTED_PROXY_COUNT`` is set to the
    number of reverse proxies that append to it (1 on Render/Railway). The
    address added by the outermost trusted proxy is used.
    """
    proxy_count = getattr(settings, "TRUSTED_PROXY_COUNT", 0)
    if proxy_count > 0:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        parts = [part.strip() for part in forwarded.split(",") if part.strip()]
        if len(parts) >= proxy_count:
            return parts[-proxy_count]
    return request.META.get("REMOTE_ADDR")


def get_axes_username(request, credentials) -> str:
    """Normalise the submitted email so case changes cannot bypass throttling."""
    username = ""
    if credentials:
        username = credentials.get("username") or credentials.get("email") or ""
    if not username and request is not None and request.method == "POST":
        username = request.POST.get("username", "")
    return username.strip().lower()


def safe_next_url(request, fallback: str) -> str:
    """Return the ``next`` parameter if it points to this site, else ``fallback``."""
    candidate = request.POST.get("next") or request.GET.get("next")
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return fallback
