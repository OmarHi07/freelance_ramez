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

# Email goes through Resend's HTTPS API (django-anymail): Railway Hobby blocks
# outbound SMTP. EMAIL_URL is for local development only and is never read here.
_resend_api_key = env("RESEND_API_KEY", default="").strip()
if not _resend_api_key:
    raise ImproperlyConfigured("Set RESEND_API_KEY in production: email is sent through Resend's HTTPS API.")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="").strip()
if not DEFAULT_FROM_EMAIL:
    raise ImproperlyConfigured(
        'Set DEFAULT_FROM_EMAIL in production, e.g. "rawnaq_accessories1 <orders@your-domain>" '
        "on a domain verified in Resend."
    )
SERVER_EMAIL = DEFAULT_FROM_EMAIL
EMAIL_BACKEND = "anymail.backends.resend.EmailBackend"
ANYMAIL = {
    "RESEND_API_KEY": _resend_api_key,
    # Every send keeps the EMAIL_TIMEOUT bound (password reset included); Anymail's
    # own default is 30 seconds, as long as a Gunicorn worker is allowed to live.
    "REQUESTS_TIMEOUT": EMAIL_TIMEOUT,  # noqa: F405
}

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
