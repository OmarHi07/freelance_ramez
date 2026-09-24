"""Settings shared by every environment.

Environment-specific modules (development, production, test) import from here.
All secrets and host-specific values come from environment variables; see
``.env.example`` for the full list.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import environ
from django.utils.translation import gettext_lazy as _

from config.storage import CLOUDINARY, build_media_storage, media_backend_name

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    # Values already present in the real environment always win.
    environ.Env.read_env(str(_env_file), overwrite=False)

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY", default="")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# Absolute public URL of the site (e.g. https://rawnaq.example). Used to build
# the owner-dashboard link inside WhatsApp messages. Falls back to the request host.
SITE_URL = env("SITE_URL", default="").rstrip("/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "axes",
    # Project apps
    "core",
    "accounts",
    "catalog",
    "cart",
    "orders",
    "dashboard",
]

MIDDLEWARE = [
    # Answers /healthz/ for platform probes before host validation.
    "core.middleware.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
    # AxesMiddleware should be the last middleware.
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.storefront",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Database (PostgreSQL via psycopg 3)
# ---------------------------------------------------------------------------
DATABASES = {
    "default": env.db("DATABASE_URL", default="postgres://rawnaq:rawnaq@localhost:5432/rawnaq"),
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    # Login-attempt throttling must run first.
    "axes.backends.AxesStandaloneBackend",
    "accounts.backends.EmailBackend",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "core:home"
PASSWORD_RESET_TIMEOUT = 60 * 60 * 3  # 3 hours

# django-axes: throttle repeated failed logins per (email, IP) pair.
AXES_FAILURE_LIMIT = env.int("AXES_FAILURE_LIMIT", default=5)
AXES_COOLOFF_TIME = timedelta(minutes=env.int("AXES_COOLOFF_MINUTES", default=15))
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "accounts/lockout.html"
AXES_CLIENT_IP_CALLABLE = "core.security.get_client_ip"
AXES_USERNAME_CALLABLE = "core.security.get_axes_username"
AXES_DISABLE_ACCESS_LOG = True  # do not keep a log of every successful login
AXES_VERBOSE = False  # keep emails out of application logs
# Number of trusted reverse proxies in front of Django (Render/Railway = 1).
TRUSTED_PROXY_COUNT = env.int("TRUSTED_PROXY_COUNT", default=0)

# ---------------------------------------------------------------------------
# Sessions, cookies and security headers
# ---------------------------------------------------------------------------
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_FAILURE_VIEW = "core.views.csrf_failure"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# Content-Security-Policy sent by core.middleware.SecurityHeadersMiddleware.
# No inline scripts are used anywhere in the project.
CSP_EXTRA_IMG_SRC = env.list("CSP_EXTRA_IMG_SRC", default=[])
CONTENT_SECURITY_POLICY = {
    "default-src": ["'self'"],
    "script-src": ["'self'"],
    # Brand colours are applied through validated CSS custom properties in style attributes.
    "style-src": ["'self'", "'unsafe-inline'"],
    "img-src": ["'self'", "data:", "blob:", *CSP_EXTRA_IMG_SRC],
    "font-src": ["'self'"],
    "connect-src": ["'self'"],
    "form-action": ["'self'"],
    "frame-ancestors": ["'none'"],
    "base-uri": ["'self'"],
    "object-src": ["'none'"],
}
PERMISSIONS_POLICY = "geolocation=(self), camera=(), microphone=(), payment=(), usb=()"

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "ar"
LANGUAGES = [
    ("ar", _("Arabic")),
    ("en", _("English")),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Asia/Jerusalem"
USE_I18N = True
USE_TZ = True
LANGUAGE_COOKIE_SAMESITE = "Lax"
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365

# ---------------------------------------------------------------------------
# Static and media files
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = env("MEDIA_URL", default="/media/")
MEDIA_ROOT = Path(env("MEDIA_ROOT", default=str(BASE_DIR / "media")))

MEDIA_STORAGE_BACKEND = media_backend_name(env)
# Let Django serve local media when DEBUG is off (only for a single-server setup with a persistent disk).
SERVE_MEDIA_FILES = env.bool("DJANGO_SERVE_MEDIA_FILES", default=False)
STORAGES = {
    "default": build_media_storage(env),
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
if MEDIA_STORAGE_BACKEND == CLOUDINARY:  # pragma: no cover - optional integration
    INSTALLED_APPS.append("cloudinary_storage")
    INSTALLED_APPS.append("cloudinary")

# Upload limits (bytes). Images larger than this are rejected by validators.
MAX_IMAGE_UPLOAD_SIZE = env.int("MAX_IMAGE_UPLOAD_MB", default=5) * 1024 * 1024
MAX_IMAGE_DIMENSION = 6000
IMAGE_OPTIMIZE_MAX_EDGE = 1600
IMAGE_THUMBNAIL_EDGE = 600
FILE_UPLOAD_MAX_MEMORY_SIZE = 2_621_440
DATA_UPLOAD_MAX_MEMORY_SIZE = 2_621_440
FILE_UPLOAD_PERMISSIONS = 0o644

# ---------------------------------------------------------------------------
# Email (password reset). Configure a real SMTP URL in production.
# ---------------------------------------------------------------------------
vars().update(env.email_url("EMAIL_URL", default="consolemail://"))
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Rawnaq Accessories <no-reply@localhost>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# ---------------------------------------------------------------------------
# Store behaviour
# ---------------------------------------------------------------------------
LOW_STOCK_THRESHOLD = env.int("LOW_STOCK_THRESHOLD", default=3)
MAX_CART_LINE_QUANTITY = 10
ORDER_NOTIFIER_BACKEND = env("ORDER_NOTIFIER_BACKEND", default="orders.services.notifications.ClickToChatNotifier")
ANONYMOUS_CART_MAX_AGE_DAYS = 30

# ---------------------------------------------------------------------------
# Logging: never log customer personal data (names, emails, phones, addresses).
# ---------------------------------------------------------------------------
LOG_LEVEL = env("DJANGO_LOG_LEVEL", default="INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
        "json": {"()": "core.logging.JSONFormatter"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "axes": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "rawnaq": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}
