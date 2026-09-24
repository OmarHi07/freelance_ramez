"""Settings used by the automated test suite (pytest / CI)."""

import tempfile

from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "test-only-secret-key-not-used-anywhere-else-0123456789"  # noqa: S105
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
SITE_URL = "https://shop.example.test"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="rawnaq-test-media-"))  # noqa: F405
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
LOGGING["root"]["level"] = "CRITICAL"  # noqa: F405
