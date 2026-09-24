"""Storage configuration helpers.

Keeps the choice of media backend (local disk, S3-compatible object storage, or
Cloudinary) in one place so settings modules stay declarative. Image binaries are
always stored in a storage backend and never inside PostgreSQL.
"""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured

LOCAL = "local"
S3 = "s3"
CLOUDINARY = "cloudinary"
SUPPORTED_MEDIA_BACKENDS = (LOCAL, S3, CLOUDINARY)


def build_media_storage(env) -> dict:
    """Return the ``STORAGES["default"]`` entry for the configured backend."""
    backend = env("MEDIA_STORAGE_BACKEND", default=LOCAL).strip().lower()

    if backend == LOCAL:
        return {"BACKEND": "django.core.files.storage.FileSystemStorage"}

    if backend == S3:
        # Works with AWS S3 and S3-compatible services such as Cloudflare R2,
        # Backblaze B2, DigitalOcean Spaces and MinIO.
        options = {
            "bucket_name": env("S3_BUCKET_NAME"),
            "access_key": env("S3_ACCESS_KEY_ID"),
            "secret_key": env("S3_SECRET_ACCESS_KEY"),
            "region_name": env("S3_REGION_NAME", default=None),
            "endpoint_url": env("S3_ENDPOINT_URL", default=None),
            "custom_domain": env("S3_CUSTOM_DOMAIN", default=None),
            "location": env("S3_MEDIA_LOCATION", default="media"),
            "default_acl": env("S3_DEFAULT_ACL", default=None),
            "querystring_auth": env.bool("S3_QUERYSTRING_AUTH", default=False),
            "file_overwrite": False,
            "object_parameters": {"CacheControl": "public, max-age=31536000, immutable"},
        }
        return {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {key: value for key, value in options.items() if value is not None},
        }

    if backend == CLOUDINARY:
        # Optional dependency, see requirements-cloudinary.txt and README.
        if not env("CLOUDINARY_URL", default=""):
            raise ImproperlyConfigured("CLOUDINARY_URL is required when MEDIA_STORAGE_BACKEND=cloudinary.")
        return {"BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage"}

    raise ImproperlyConfigured(
        f"Unsupported MEDIA_STORAGE_BACKEND={backend!r}. Choose one of: {', '.join(SUPPORTED_MEDIA_BACKENDS)}."
    )


def media_backend_name(env) -> str:
    return env("MEDIA_STORAGE_BACKEND", default=LOCAL).strip().lower()
