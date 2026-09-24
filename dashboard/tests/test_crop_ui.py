"""The crop editor is wired into every owner image field, and degrades gracefully."""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import translation

from catalog.models import ProductImage
from conftest import make_brand, make_category, make_product, uploaded_image
from core.images import BRAND_BANNER, BRAND_LOGO, CATEGORY_IMAGE, PRODUCT_IMAGE

pytestmark = pytest.mark.django_db

VENDOR = Path(settings.BASE_DIR) / "static" / "vendor" / "cropperjs"


def url(name, **kwargs):
    with translation.override("en"):
        return reverse(f"dashboard:{name}", kwargs=kwargs or None)


def test_the_crop_library_is_vendored_locally_with_its_licence():
    for filename in ("cropper.min.js", "cropper.min.css", "LICENSE"):
        assert (VENDOR / filename).is_file(), filename
    assert "MIT" in (VENDOR / "LICENSE").read_text(encoding="utf-8")


def test_our_dialog_classes_do_not_collide_with_the_library():
    """Cropper.js styles its own overlay `.cropper-modal`, so we must not reuse its names.

    Sharing a class name silently applied our full-screen dialog styles to the
    library's internal drag box.
    """
    ours = (Path(settings.BASE_DIR) / "static" / "js" / "image-cropper.js").read_text(encoding="utf-8")
    library = set(re.findall(r"\.(cropper-[A-Za-z0-9_-]+)", (VENDOR / "cropper.min.css").read_text(encoding="utf-8")))
    assert "cropper-modal" in library, "this guard assumes the library styles .cropper-modal"

    assigned = re.findall(r'className = "([^"]+)"', ours) + re.findall(r'classList\.add\("([^"]+)"\)', ours)
    created = {part for value in assigned for part in value.split()}
    assert not (created & library), sorted(created & library)


def test_no_dashboard_asset_is_loaded_from_a_cdn(staff_client, site_settings):
    html = staff_client.get(url("overview")).content.decode()
    for source in re.findall(r'(?:src|href)="([^"]+)"', html):
        assert not source.startswith(("http://", "https://", "//")), source
    assert "vendor/cropperjs/cropper.min.js" in html
    assert "js/image-cropper.js" in html


def test_dashboard_pages_still_have_no_inline_scripts(staff_client, site_settings):
    product = make_product()
    targets = [
        url("product_create"),
        url("product_update", pk=product.pk),
        url("brand_create"),
        url("category_create"),
    ]
    for target in targets:
        html = staff_client.get(target).content.decode()
        assert not re.search(r"<script(?![^>]*\ssrc=)[^>]*>", html), target
        assert "javascript:" not in html, target


@pytest.mark.parametrize(
    ("page", "field", "target", "shape"),
    [
        ("brand_create", "logo", BRAND_LOGO, "circle"),
        ("brand_create", "banner_image", BRAND_BANNER, "square"),
        ("category_create", "image", CATEGORY_IMAGE, "square"),
    ],
)
def test_brand_and_category_image_fields_declare_their_crop_target(
    staff_client, site_settings, page, field, target, shape
):
    html = staff_client.get(url(page)).content.decode()
    tag = re.search(rf'<input[^>]*name="{field}"[^>]*>', html).group(0)
    assert f'data-crop="{target.name}"' in tag
    assert f'data-crop-ratio="{target.ratio_w}/{target.ratio_h}"' in tag
    assert f'data-crop-shape="{shape}"' in tag
    assert f'data-crop-width="{target.max_width}"' in tag
    assert f'data-crop-height="{target.max_height}"' in tag
    # Without JavaScript this is still an ordinary file input.
    assert 'type="file"' in tag


def test_new_product_images_can_still_be_selected_several_at_a_time(staff_client, site_settings):
    html = staff_client.get(url("product_create")).content.decode()
    tag = re.search(r'<input[^>]*name="new_images"[^>]*>', html).group(0)
    assert "multiple" in tag
    assert f'data-crop="{PRODUCT_IMAGE.name}"' in tag
    assert 'data-crop-ratio="1/1"' in tag


def test_crop_modal_labels_are_translated(staff_client, site_settings):
    english = staff_client.get(url("brand_create")).content.decode()
    assert 'data-crop-apply="Use this crop"' in english

    with translation.override("ar"):
        arabic_url = reverse("dashboard:brand_create")
    arabic = staff_client.get(arabic_url).content.decode()
    tag = re.search(r'<input[^>]*name="logo"[^>]*>', arabic).group(0)
    apply_label = re.search(r'data-crop-apply="([^"]*)"', tag).group(1)
    assert apply_label and apply_label != "Use this crop"


def test_existing_images_offer_an_adjust_crop_action(staff_client, site_settings):
    brand = make_brand()
    brand.logo = uploaded_image("logo.png", size=(600, 600))
    brand.save()
    html = staff_client.get(url("brand_update", pk=brand.pk)).content.decode()
    assert f'data-crop-adjust="{brand.logo.url}"' in html
    assert 'data-crop-adjust-for="id_logo"' in html

    product = make_product()
    image = ProductImage.objects.create(product=product, image=uploaded_image("p.png", size=(600, 600)))
    html = staff_client.get(url("product_update", pk=product.pk)).content.decode()
    assert f'data-crop-adjust="{image.image.url}"' in html
    assert 'data-crop-adjust-for="id_images-0-image"' in html


def test_existing_product_images_expose_a_replacement_file_input(staff_client, site_settings):
    product = make_product()
    ProductImage.objects.create(product=product, image=uploaded_image("p.png", size=(600, 600)))
    html = staff_client.get(url("product_update", pk=product.pk)).content.decode()
    tag = re.search(r'<input[^>]*name="images-0-image"[^>]*>', html).group(0)
    assert 'type="file"' in tag
    # No "clear" checkbox: an image is removed with the row delete tick instead.
    assert 'name="images-0-image-clear"' not in html


def test_saving_a_product_without_choosing_a_replacement_keeps_the_image(staff_client, site_settings):
    product = make_product()
    image = ProductImage.objects.create(product=product, image=uploaded_image("p.png", size=(600, 600)))
    before = (image.image.name, image.thumbnail.name)

    category = make_category()
    data = {
        "brand": product.brand.pk,
        "categories": [category.pk],
        "name_ar": product.name_ar,
        "name_en": product.name_en,
        "slug": product.slug,
        "description_ar": "",
        "description_en": "",
        "regular_price": str(product.regular_price),
        "verification_status": "CONFIRMED",
        "is_active": "on",
        "variants-TOTAL_FORMS": "1",
        "variants-INITIAL_FORMS": "1",
        "variants-MIN_NUM_FORMS": "0",
        "variants-MAX_NUM_FORMS": "1000",
        "variants-0-id": str(product.variants.first().pk),
        "variants-0-option_mode": "custom",
        "variants-0-name_ar": "خيار 1",
        "variants-0-name_en": "Option 1",
        "variants-0-stock_quantity": "10",
        "variants-0-display_order": "0",
        "variants-0-is_active": "on",
        "images-TOTAL_FORMS": "1",
        "images-INITIAL_FORMS": "1",
        "images-MIN_NUM_FORMS": "0",
        "images-MAX_NUM_FORMS": "1000",
        "images-0-id": str(image.pk),
        "images-0-display_order": "0",
        "images-0-is_primary": "on",
    }
    response = staff_client.post(url("product_update", pk=product.pk), data)
    assert response.status_code == 302, response.context and response.context["form"].errors

    image.refresh_from_db()
    assert (image.image.name, image.thumbnail.name) == before


def test_a_low_resolution_upload_is_accepted_with_a_warning(staff_client, site_settings):
    response = staff_client.post(
        url("brand_create"),
        {
            "name_en": "Tiny",
            "name_ar": "صغير",
            "slug": "tiny-logo",
            "primary_color": "#F8C8DC",
            "secondary_color": "#9E526F",
            "display_order": 0,
            "is_active": "on",
            "logo": uploaded_image("small.png", size=(120, 120)),
        },
        follow=True,
    )
    assert response.status_code == 200
    from catalog.models import Brand

    brand = Brand.objects.get(slug="tiny-logo")
    assert brand.logo, "the upload must still be saved"
    texts = [str(message) for message in response.context["messages"]]
    assert any("small" in text for text in texts), texts
