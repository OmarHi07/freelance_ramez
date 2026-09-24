"""Production settings (Render, Railway, Docker).

Fails fast when required configuration is missing so a misconfigured deploy
never serves traffic with insecure defaults.
"""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import env

DEBUG = False

if not SECRET_KEY or SECRET_KEY.startswith("django-insecure") or len(SECRET_KEY) < 40:  # noqa: F405
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY to a long random value (50+ characters) in production.")
if not ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("Set DJANGO_ALLOWED_HOSTS (comma separated) in production.")
if not env("DATABASE_URL", default=""):
    raise ImproperlyConfigured("Set DATABASE_URL in production.")

# HTTPS
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_REDIRECT_EXEMPT = [r"^healthz/?$"]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=3600)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
SECURE_HSTS_PRELOAD = env.bool("DJANGO_SECURE_HSTS_PRELOAD", default=False)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
LANGUAGE_COOKIE_SECURE = True

# Render and Railway put exactly one proxy in front of the app.
TRUSTED_PROXY_COUNT = env.int("TRUSTED_PROXY_COUNT", default=1)

# Hashed, compressed static files served by WhiteNoise.
STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Structured (JSON) logs on stdout for the hosting platform's log drain.
LOGGING["handlers"]["console"]["formatter"] = "json"  # noqa: F405
