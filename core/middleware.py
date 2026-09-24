"""Health-check short circuit and additional security headers."""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger("rawnaq.core")

HEALTH_PATHS = {"/healthz", "/healthz/"}


def health_response() -> JsonResponse:
    """Liveness/readiness payload: checks that PostgreSQL answers ``SELECT 1``."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:  # pragma: no cover - only when the database is down
        logger.exception("Health check database probe failed")
        response = JsonResponse({"status": "error", "database": "unavailable"}, status=503)
    else:
        response = JsonResponse({"status": "ok", "database": "ok"})
    response["Cache-Control"] = "no-store"
    return response


class HealthCheckMiddleware:
    """Answer ``/healthz/`` before host validation and HTTPS redirects.

    Platform probes (Render, Railway, Docker HEALTHCHECK) call the container
    with internal host names that are not in ``ALLOWED_HOSTS``. The endpoint
    exposes no data beyond "ok"/"error".
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info in HEALTH_PATHS and request.method in ("GET", "HEAD"):
            return health_response()
        return self.get_response(request)


def build_csp(policy: dict[str, list[str]]) -> str:
    return "; ".join(f"{directive} {' '.join(sources)}" for directive, sources in policy.items())


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.csp = build_csp(settings.CONTENT_SECURITY_POLICY)
        self.permissions_policy = settings.PERMISSIONS_POLICY

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault("Content-Security-Policy", self.csp)
        response.headers.setdefault("Permissions-Policy", self.permissions_policy)
        return response
