"""Server-side image pipeline: crop fallback, privacy stripping and safe replacement."""

import io

import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from catalog.models import Brand, Category, ProductImage
from conftest import make_brand, make_category, make_product
from core.images import (
    BRAND_BANNER,
    BRAND_LOGO,
    CATEGORY_IMAGE,
    PRODUCT_IMAGE,
    center_crop,
    crop_and_optimize,
    is_low_resolution,
)

pytestmark = pytest.mark.django_db

RED = (220, 40, 40)
BLUE = (40, 60, 220)


def photo(size=(1200, 600), fmt="JPEG", exif=None, color=(248, 200, 220)) -> SimpleUploadedFile:
    buffer = io.BytesIO()
    image = Image.new("RGB", size, color)
    kwargs = {"exif": exif} if exif else {}
    image.save(buffer, format=fmt, **kwargs)
    content_type = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}[fmt]
    return SimpleUploadedFile(f"photo.{fmt.lower()}", buffer.getvalue(), content_type=content_type)


def split_photo(size=(400, 200), exif=None) -> SimpleUploadedFile:
    """Left half red, right half blue — so a rotation is visible in the result."""
    image = Image.new("RGB", size, RED)
    image.paste(Image.new("RGB", (size[0] // 2, size[1]), BLUE), (size[0] // 2, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", **({"exif": exif} if exif else {}))
    return SimpleUploadedFile("split.jpg", buffer.getvalue(), content_type="image/jpeg")


def stored_size(field_file) -> tuple[int, int]:
    with field_file.open("rb") as handle, Image.open(handle) as image:
        return image.size


def ratio_of(size) -> float:
    return size[0] / size[1]


# ---------------------------------------------------------------------------
# Server-side crop fallback (an uncropped upload still ends up the right shape)
# ---------------------------------------------------------------------------
def test_brand_logo_falls_back_to_a_square(site_settings):
    brand = make_brand()
    brand.logo = photo(size=(1200, 600))
    brand.save()
    width, height = stored_size(brand.logo)
    assert width == height
    assert width <= BRAND_LOGO.max_width


def test_category_image_falls_back_to_a_square(site_settings):
    category = make_category()
    category.image = photo(size=(1400, 500))
    category.save()
    width, height = stored_size(category.image)
    assert width == height
    assert width <= CATEGORY_IMAGE.max_width


def test_product_image_falls_back_to_a_square(site_settings):
    product = make_product()
    image = ProductImage.objects.create(product=product, image=photo(size=(1800, 700)))
    assert stored_size(image.image)[0] == stored_size(image.image)[1]
    assert (image.width, image.height) == stored_size(image.image)
    assert image.width <= PRODUCT_IMAGE.max_width


def test_brand_banner_falls_back_to_16_by_5(site_settings):
    brand = make_brand()
    brand.banner_image = photo(size=(1200, 1200))
    brand.save()
    size = stored_size(brand.banner_image)
    assert BRAND_BANNER.matches(*size), size
    assert size[0] <= BRAND_BANNER.max_width and size[1] <= BRAND_BANNER.max_height


def test_a_correctly_cropped_upload_is_not_cropped_again():
    """Framing the browser already produced is kept exactly as it is."""
    square = Image.new("RGB", (900, 900), RED)
    assert center_crop(square, PRODUCT_IMAGE) is square

    banner = Image.new("RGB", (1600, 500), RED)
    assert center_crop(banner, BRAND_BANNER) is banner

    # Rounding in the browser canvas stays inside the tolerance.
    nearly = Image.new("RGB", (1601, 500), RED)
    assert center_crop(nearly, BRAND_BANNER) is nearly


def test_crop_keeps_the_centre_of_the_picture():
    wide = Image.new("RGB", (400, 200), RED)
    wide.paste(Image.new("RGB", (100, 200), BLUE), (150, 0))  # blue stripe down the middle
    cropped = center_crop(wide, PRODUCT_IMAGE)
    assert cropped.size == (200, 200)
    assert cropped.getpixel((100, 100)) == BLUE


def test_small_images_are_never_upscaled():
    tiny = photo(size=(120, 120), fmt="PNG")
    result = crop_and_optimize(tiny, PRODUCT_IMAGE)
    with Image.open(io.BytesIO(result.read())) as image:
        assert image.size == (120, 120)


def test_low_resolution_sources_are_flagged():
    assert is_low_resolution(photo(size=(200, 200), fmt="PNG"), PRODUCT_IMAGE)
    assert not is_low_resolution(photo(size=(1600, 1600), fmt="PNG"), PRODUCT_IMAGE)


# ---------------------------------------------------------------------------
# Privacy and orientation
# ---------------------------------------------------------------------------
def orientation_exif(value: int) -> bytes:
    exif = Image.Exif()
    exif[0x0112] = value  # Orientation
    exif[0x010E] = "secret location note"  # ImageDescription, must not survive
    return exif.tobytes()


def test_exif_rotation_is_applied_and_metadata_is_stripped(site_settings):
    # Orientation 6 means the stored pixels must be turned a quarter turn to
    # display correctly, which turns the left/right split into a top/bottom one.
    upload = split_photo(size=(400, 200), exif=orientation_exif(6))
    product = make_product()
    image = ProductImage.objects.create(product=product, image=upload)

    with image.image.open("rb") as handle, Image.open(handle) as stored:
        assert stored.format == "WEBP"
        assert not stored.getexif()
        assert b"secret location note" not in image.image.read()
        width, height = stored.size
        rgb = stored.convert("RGB")
        top = rgb.getpixel((width // 2, height // 6))
        bottom = rgb.getpixel((width // 2, height * 5 // 6))
        left = rgb.getpixel((width // 6, height // 2))
        right = rgb.getpixel((width * 5 // 6, height // 2))

    def near(pixel, expected):
        return all(abs(a - b) < 40 for a, b in zip(pixel, expected, strict=True))

    assert not near(top, bottom), "the EXIF rotation was not applied"
    assert near(left, right), "the picture is still split left/right, so it was not rotated"


def test_stored_filenames_are_random_and_do_not_leak_the_original(site_settings):
    brand = make_brand()
    brand.logo = SimpleUploadedFile(
        "my-holiday-photo-2024.jpg", photo(size=(600, 600)).read(), content_type="image/jpeg"
    )
    brand.save()
    assert "holiday" not in brand.logo.name
    assert brand.logo.name.endswith(".webp")


# ---------------------------------------------------------------------------
# Replacement: regenerate thumbnails, delete old files only after commit
# ---------------------------------------------------------------------------
def test_replacing_a_product_image_regenerates_the_thumbnail(site_settings, settings):
    settings.IMAGE_THUMBNAIL_EDGE = 120
    product = make_product()
    image = ProductImage.objects.create(product=product, image=photo(size=(1000, 1000), color=RED))
    first_thumb = image.thumbnail.name
    assert stored_size(image.thumbnail) == (120, 120)

    image.image = photo(size=(900, 300), color=BLUE)
    image.save()
    image.refresh_from_db()

    assert image.thumbnail.name != first_thumb, "a replacement must produce a fresh thumbnail"
    assert stored_size(image.thumbnail) == (120, 120)
    # The thumbnail comes from the new file, not the old one.
    with image.thumbnail.open("rb") as handle, Image.open(handle) as thumb:
        pixel = thumb.convert("RGB").getpixel((60, 60))
    assert all(abs(a - b) < 40 for a, b in zip(pixel, BLUE, strict=True))


def test_old_image_and_thumbnail_are_deleted_only_after_the_commit(site_settings, django_capture_on_commit_callbacks):
    product = make_product()
    image = ProductImage.objects.create(product=product, image=photo(size=(800, 800)))
    old_image, old_thumb = image.image.name, image.thumbnail.name
    assert default_storage.exists(old_image) and default_storage.exists(old_thumb)

    with django_capture_on_commit_callbacks(execute=True):
        image.image = photo(size=(800, 800), color=BLUE)
        image.save()
        # Still present while the transaction is open.
        assert default_storage.exists(old_image)

    assert not default_storage.exists(old_image)
    assert not default_storage.exists(old_thumb)
    image.refresh_from_db()
    assert default_storage.exists(image.image.name)
    assert default_storage.exists(image.thumbnail.name)


def test_a_rolled_back_save_keeps_the_existing_files(site_settings, django_capture_on_commit_callbacks):
    product = make_product()
    image = ProductImage.objects.create(product=product, image=photo(size=(800, 800)))
    old_image = image.image.name

    with django_capture_on_commit_callbacks(execute=False):
        image.image = photo(size=(800, 800), color=BLUE)
        image.save()
    # The callbacks were never executed, so nothing was removed.
    assert default_storage.exists(old_image)


@pytest.mark.parametrize("model_field", [("brand", "logo"), ("brand", "banner_image"), ("category", "image")])
def test_saving_without_a_new_file_leaves_the_stored_image_alone(site_settings, model_field):
    kind, field = model_field
    if kind == "brand":
        obj = make_brand()
        setattr(obj, field, photo(size=(900, 900)))
    else:
        obj = make_category()
        setattr(obj, field, photo(size=(900, 900)))
    obj.save()
    stored_name = getattr(obj, field).name
    stored_bytes = getattr(obj, field).read()

    obj.name_en = "Renamed without touching the picture"
    obj.save()
    obj.refresh_from_db()

    assert getattr(obj, field).name == stored_name
    assert getattr(obj, field).read() == stored_bytes
    assert default_storage.exists(stored_name)


def test_clearing_a_brand_logo_removes_the_file_after_commit(site_settings, django_capture_on_commit_callbacks):
    brand = make_brand()
    brand.logo = photo(size=(700, 700))
    brand.save()
    old_name = brand.logo.name

    with django_capture_on_commit_callbacks(execute=True):
        brand.logo = None
        brand.save()

    assert not default_storage.exists(old_name)


# ---------------------------------------------------------------------------
# Rejections still hold
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "bad",
    [
        SimpleUploadedFile("vector.svg", b"<svg onload='alert(1)'></svg>", content_type="image/svg+xml"),
        SimpleUploadedFile("anim.gif", b"GIF89a\x01\x00\x01\x00\x00\x00\x00;", content_type="image/gif"),
        SimpleUploadedFile("fake.png", b"not an image at all", content_type="image/png"),
    ],
)
def test_invalid_files_are_still_rejected_by_the_model_validators(site_settings, bad):
    brand = Brand(name_en="X", name_ar="X", slug="x-reject", logo=bad)
    with pytest.raises(ValidationError):
        brand.full_clean()


def test_oversized_files_are_still_rejected(site_settings, settings):
    settings.MAX_IMAGE_UPLOAD_SIZE = 512
    big = photo(size=(900, 900), fmt="PNG")
    category = Category(name_en="X", name_ar="X", slug="x-big", image=big)
    with pytest.raises(ValidationError):
        category.full_clean()


def test_dimension_limit_is_still_enforced(site_settings, settings):
    settings.MAX_IMAGE_DIMENSION = 300
    category = Category(name_en="X", name_ar="X", slug="x-dims", image=photo(size=(900, 900), fmt="PNG"))
    with pytest.raises(ValidationError):
        category.full_clean()


def test_crop_and_optimize_always_produces_webp():
    result = crop_and_optimize(photo(size=(900, 400), fmt="PNG"), CATEGORY_IMAGE)
    assert isinstance(result, ContentFile)
    with Image.open(io.BytesIO(result.read())) as image:
        assert image.format == "WEBP"
        assert ratio_of(image.size) == pytest.approx(1.0)
