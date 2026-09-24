"""Image optimisation used for every uploaded catalogue image.

Uploaded images are re-encoded to WebP, resized to a sensible maximum edge,
auto-rotated according to EXIF orientation and stripped of all metadata
(EXIF can contain GPS coordinates). Thumbnails are produced the same way.
"""

from __future__ import annotations

import io
import uuid
from datetime import date

from django.core.files.base import ContentFile
from django.utils.deconstruct import deconstructible
from PIL import Image, ImageOps

WEBP_QUALITY = 82


def _prepare(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    if image.mode in ("P", "LA"):
        image = image.convert("RGBA")
    elif image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")
    return image


def optimize_image(source, *, max_edge: int, quality: int = WEBP_QUALITY) -> ContentFile:
    """Return a new WebP ``ContentFile`` no larger than ``max_edge`` on its longest side."""
    if hasattr(source, "seek"):
        source.seek(0)
    with Image.open(source) as original:
        original.load()
        image = _prepare(original)
        image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="WEBP", quality=quality, method=4)
    return ContentFile(buffer.getvalue())


def image_dimensions(source) -> tuple[int, int] | None:
    try:
        if hasattr(source, "seek"):
            source.seek(0)
        with Image.open(source) as image:
            return image.size
    except OSError:
        return None


@deconstructible
class UploadTo:
    """Store uploads under ``<prefix>/<year>/<month>/<random>.webp``.

    Original filenames are discarded so they cannot leak personal data or
    collide with other uploads.
    """

    def __init__(self, prefix: str):
        self.prefix = prefix.strip("/")

    def __call__(self, instance, filename: str) -> str:
        today = date.today()
        return f"{self.prefix}/{today:%Y}/{today:%m}/{uuid.uuid4().hex}.webp"

    def __eq__(self, other) -> bool:
        return isinstance(other, UploadTo) and other.prefix == self.prefix


def optimize_field_if_new(instance, field_name: str, max_edge: int) -> bool:
    """Re-encode a newly assigned ImageField value in place. Returns True if it changed."""
    field_file = getattr(instance, field_name)
    if not field_file or getattr(field_file, "_committed", True):
        return False
    optimized = optimize_image(field_file.file, max_edge=max_edge)
    field_file.save(field_file.name or "upload.webp", optimized, save=False)
    return True


def delete_file_on_commit(field_file) -> None:
    """Delete a stored file once the surrounding transaction commits."""
    from django.db import transaction

    if not field_file:
        return
    storage, name = field_file.storage, field_file.name
    if name:
        transaction.on_commit(lambda: storage.delete(name))


def delete_replaced_files(
    instance, field_names: list[str], *, only_uncommitted: bool = False, force: bool = False
) -> None:
    """Schedule deletion of files that are being replaced on an existing row.

    With ``only_uncommitted`` a field is only considered when a new, not yet
    stored file has been assigned to it (or it has been cleared). With ``force``
    the previously stored files are always scheduled for deletion.
    """
    if not instance.pk:
        return
    model = type(instance)
    old = model.objects.filter(pk=instance.pk).values(*field_names).first()
    if not old:
        return
    for name in field_names:
        old_name = old.get(name)
        if not old_name:
            continue
        current = getattr(instance, name)
        if force:
            current = None
        elif only_uncommitted and current and getattr(current, "_committed", True):
            continue
        if not current or current.name != old_name:
            storage = model._meta.get_field(name).storage
            from django.db import transaction

            transaction.on_commit(lambda storage=storage, old_name=old_name: storage.delete(old_name))
