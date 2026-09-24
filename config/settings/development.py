"""Local development settings."""

import warnings

from .base import *  # noqa: F403
from .base import env

DEBUG = env.bool("DJANGO_DEBUG", default=True)
SECRET_KEY = SECRET_KEY or "django-insecure-local-development-key-change-me"
ALLOWED_HOSTS = ALLOWED_HOSTS or ["localhost", "127.0.0.1", "[::1]"]
INTERNAL_IPS = ["127.0.0.1"]

# Serve files straight from app/static folders without running collectstatic.
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True
warnings.filterwarnings("ignore", message="No directory at", module="whitenoise.base")
