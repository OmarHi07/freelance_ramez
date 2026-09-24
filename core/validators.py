"""Reusable validators for colours, phone numbers and uploaded images."""

from __future__ import annotations

import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, RegexValidator
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _
from PIL import Image, UnidentifiedImageError

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

hex_color_validator = RegexValidator(
    regex=HEX_COLOR_RE,
    message=_("Enter a colour as a six-digit hexadecimal value, for example #F8C8DC."),
    code="invalid_hex_color",
)

international_phone_validator = RegexValidator(
    regex=r"^[1-9][0-9]{7,14}$",
    message=_("Use digits only, including the country code, without + or spaces (for example 972553003327)."),
    code="invalid_international_phone",
)

customer_phone_validator = RegexValidator(
    regex=r"^\+?[0-9][0-9 \-]{7,18}[0-9]$",
    message=_("Enter a valid phone number, for example 0501234567."),
    code="invalid_phone",
)

ALLOWED_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}

image_extension_validator = FileExtensionValidator(allowed_extensions=ALLOWED_IMAGE_EXTENSIONS)


def is_valid_hex_color(value: str | None) -> bool:
    return bool(value) and bool(HEX_COLOR_RE.match(value))


def normalize_phone(value: str) -> str:
    """Remove spaces and dashes from a phone number, keeping a leading +."""
    value = (value or "").strip()
    prefix = "+" if value.startswith("+") else ""
    digits = re.sub(r"\D", "", value)
    return f"{prefix}{digits}"


@deconstructible
class ImageUploadValidator:
    """Validate size, real format and dimensions of an uploaded image.

    The file extension alone is never trusted: Pillow must be able to parse the
    file and its detected format must be JPEG, PNG or WebP. SVG is not accepted.
    """

    def __call__(self, file) -> None:
        if file is None:
            return
        # Files already stored (e.g. re-saving a model) are not re-validated.
        if getattr(file, "_committed", False) and not hasattr(file, "content_type"):
            return
        max_size = settings.MAX_IMAGE_UPLOAD_SIZE
        size = getattr(file, "size", None)
        if size is not None and size > max_size:
            raise ValidationError(
                _("Image files must be smaller than %(size)s MB.") % {"size": max_size // (1024 * 1024)},
                code="file_too_large",
            )
        position = file.tell() if hasattr(file, "tell") else None
        try:
            file.seek(0)
            with Image.open(file) as image:
                image_format = image.format
                width, height = image.size
                image.verify()
        except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
            raise ValidationError(_("Upload a valid JPEG, PNG or WebP image."), code="invalid_image") from exc
        finally:
            if position is not None:
                file.seek(position)
        if image_format not in ALLOWED_IMAGE_FORMATS:
            raise ValidationError(_("Upload a valid JPEG, PNG or WebP image."), code="invalid_image_format")
        limit = settings.MAX_IMAGE_DIMENSION
        if width > limit or height > limit:
            raise ValidationError(
                _("Images must be at most %(limit)s pixels wide and tall.") % {"limit": limit},
                code="image_too_large",
            )

    def __eq__(self, other) -> bool:
        return isinstance(other, ImageUploadValidator)


validate_image_upload = ImageUploadValidator()
IMAGE_VALIDATORS = [image_extension_validator, validate_image_upload]
