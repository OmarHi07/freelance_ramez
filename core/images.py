"""Image optimisation used for every uploaded catalogue image.

Uploaded images are re-encoded to WebP, resized to a sensible maximum edge,
auto-rotated according to EXIF orientation and stripped of all metadata
(EXIF can contain GPS coordinates). Thumbnails are produced the same way.

Every kind of image has a fixed shape on the storefront, described by a
:class:`CropTarget`. The dashboard cropper normally sends a file that already
has the right aspect ratio; the server still centre-crops anything that does
not, so a plain upload (JavaScript off, an old bookmark, a forged request)
always ends up the right shape. Browser output is never trusted.
"""

from __future__ import annotations

import io
import uuid
from dataclasses import dataclass, replace
from datetime import date

from django.core.files.base import ContentFile
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps

WEBP_QUALITY = 82

# A crop this close to the target counts as already correct, so framing the
# owner chose by hand is never nudged by rounding in the browser canvas.
ASPECT_TOLERANCE = 0.01


@dataclass(frozen=True)
class CropTarget:
    """The shape and maximum stored size of one kind of image."""

    name: str
    ratio_w: int
    ratio_h: int
    max_width: int
    max_height: int

    @property
    def ratio(self) -> float:
        return self.ratio_w / self.ratio_h

    @property
    def css_ratio(self) -> str:
        return f"{self.ratio_w} / {self.ratio_h}"

    def matches(self, width: int, height: int) -> bool:
        """True when ``width``/``height`` already has the target aspect ratio."""
        if not width or not height:
            return False
        return abs((width / height) - self.ratio) <= ASPECT_TOLERANCE * self.ratio


BRAND_LOGO = CropTarget("brand_logo", 1, 1, 800, 800)
BRAND_BANNER = CropTarget("brand_banner", 16, 5, 1920, 600)
CATEGORY_IMAGE = CropTarget("category_image", 1, 1, 800, 800)
PRODUCT_IMAGE = CropTarget("product_image", 1, 1, 1600, 1600)

# Below this share of the stored size the result looks soft. The owner is
# warned, the upload is still accepted, and it is never upscaled.
LOW_RESOLUTION_FACTOR = 0.5


def capped(target: CropTarget, max_edge: int) -> CropTarget:
    """The same shape, never larger than ``max_edge`` on either side.

    Product images and their thumbnails share one shape but take their size
    limits from settings, so the two stay configurable independently.
    """
    return replace(target, max_width=min(target.max_width, max_edge), max_height=min(target.max_height, max_edge))


def _prepare(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    if image.mode in ("P", "LA"):
        image = image.convert("RGBA")
    elif image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")
    return image


def center_crop(image: Image.Image, target: CropTarget) -> Image.Image:
    """Centre-crop ``image`` to the target aspect ratio, or return it untouched.

    An image the browser already cropped correctly comes back unchanged.
    """
    width, height = image.size
    if target.matches(width, height):
        return image
    if width / height > target.ratio:
        new_width = max(1, round(height * target.ratio))
        left = (width - new_width) // 2
        box = (left, 0, left + new_width, height)
    else:
        new_height = max(1, round(width / target.ratio))
        top = (height - new_height) // 2
        box = (0, top, width, top + new_height)
    return image.crop(box)


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


def crop_and_optimize(source, target: CropTarget, *, quality: int = WEBP_QUALITY) -> ContentFile:
    """Centre-crop to ``target``, shrink to its maximum size and re-encode as WebP.

    EXIF rotation is applied first and every piece of metadata is dropped,
    because the result is written from a fresh buffer. Small images are never
    upscaled: they are cropped and kept at their own resolution.
    """
    if hasattr(source, "seek"):
        source.seek(0)
    with Image.open(source) as original:
        original.load()
        image = center_crop(_prepare(original), target)
        # thumbnail() only ever shrinks, so a small source keeps its resolution.
        image.thumbnail((target.max_width, target.max_height), Image.Resampling.LANCZOS)
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


def is_low_resolution(source, target: CropTarget) -> bool:
    """True when the source is much smaller than the stored size for ``target``."""
    size = image_dimensions(source)
    if not size:
        return False
    width, height = size
    return width < target.max_width * LOW_RESOLUTION_FACTOR and height < target.max_height * LOW_RESOLUTION_FACTOR


def low_resolution_warning(target: CropTarget) -> str:
    return _(
        "That picture is small (ideally at least %(width)s×%(height)s pixels), so it may look "
        "soft on the website. It was saved anyway."
    ) % {"width": target.max_width, "height": target.max_height}


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


def optimize_field_if_new(instance, field_name: str, target: CropTarget) -> bool:
    """Crop and re-encode a newly assigned ImageField value in place.

    Returns True when the field held a new upload. Files already stored are
    left alone, so saving a form without choosing a replacement never rewrites
    or re-crops the existing image.
    """
    field_file = getattr(instance, field_name)
    if not field_file or getattr(field_file, "_committed", True):
        return False
    optimized = crop_and_optimize(field_file.file, target)
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
    the previously stored files are always scheduled for deletion. Deletions run
    on commit, so a rolled-back save never removes a file that is still in use.
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
