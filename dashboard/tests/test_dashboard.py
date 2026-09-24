import io
import os
import uuid
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import URLPattern, reverse
from django.utils import translation
from PIL import Image

from catalog.models import Brand, Category, Product, ProductImage, Promotion
from conftest import make_brand, make_category, make_product, make_promotion, uploaded_image
from dashboard import urls as dashboard_urls

pytestmark = pytest.mark.django_db


def url(name, **kwargs):
    with translation.override("en"):
        return reverse(f"dashboard:{name}", kwargs=kwargs or None)


def all_dashboard_urls(ids):
    """Every route in dashboard/urls.py with realistic arguments."""
    urls = []
    for pattern in dashboard_urls.urlpatterns:
        assert isinstance(pattern, URLPattern)
        converters = pattern.pattern.converters
        kwargs = {}
        for key, converter in converters.items():
            kwargs[key] = ids["uuid"] if converter.__class__.__name__ == "UUIDConverter" else ids[pattern.name]
        urls.append((pattern.name, url(pattern.name, **kwargs)))
    return urls


@pytest.fixture
def ids(site_settings, customer):
    brand = make_brand()
    product = make_product(brand)
    category = make_category()
    promotion = make_promotion()
    return {
        "uuid": uuid.uuid4(),
        "product_update": product.pk,
        "product_delete": product.pk,
        "stock_update": product.variants.first().pk,
        "brand_update": brand.pk,
        "brand_delete": brand.pk,
        "category_update": category.pk,
        "category_delete": category.pk,
        "promotion_update": promotion.pk,
        "promotion_delete": promotion.pk,
        "customer_detail": customer.pk,
    }


def test_every_dashboard_route_is_wrapped_with_staff_check():
    for pattern in dashboard_urls.urlpatterns:
        assert getattr(pattern.callback, "staff_required", False), pattern.name


def test_anonymous_users_are_redirected_to_login(client, ids):
    for name, target in all_dashboard_urls(ids):
        for method in (client.get, client.post):
            response = method(target)
            assert response.status_code == 302, name
            assert "/account/login/" in response["Location"], name


def test_customers_get_403_everywhere(customer_client, ids):
    for name, target in all_dashboard_urls(ids):
        assert customer_client.get(target).status_code == 403, name
        assert customer_client.post(target).status_code == 403, name


def test_staff_can_open_every_page(staff_client, ids):
    post_only = {"order_status", "order_notes", "stock_update"}
    for name, target in all_dashboard_urls(ids):
        response = staff_client.get(target)
        if name in post_only:
            assert response.status_code == 405, name
        elif name.startswith("order_detail"):
            assert response.status_code == 404, name  # random UUID
        else:
            assert response.status_code == 200, name


def test_inactive_staff_user_is_rejected(client, staff_user):
    staff_user.is_active = False
    staff_user.save()
    client.force_login(staff_user)
    assert client.get(url("overview")).status_code in (302, 403)


def test_customer_cannot_create_or_delete_catalog_items(customer_client, site_settings):
    brand = make_brand()
    customer_client.post(
        url("brand_create"),
        {
            "name_en": "Hack",
            "name_ar": "x",
            "slug": "hack",
            "primary_color": "#FFFFFF",
            "secondary_color": "#000000",
            "display_order": 0,
        },
    )
    customer_client.post(url("brand_delete", pk=brand.pk))
    customer_client.post(
        url("category_create"), {"name_en": "Hack", "name_ar": "x", "slug": "hack", "display_order": 0}
    )
    assert not Brand.objects.filter(slug="hack").exists()
    assert Brand.objects.filter(pk=brand.pk).exists()
    assert not Category.objects.filter(slug="hack").exists()


def test_staff_brand_crud(staff_client, site_settings):
    response = staff_client.post(
        url("brand_create"),
        {
            "name_en": "Lulu",
            "name_ar": "لولو",
            "slug": "lulu",
            "primary_color": "#f8c8dc",
            "secondary_color": "#9E526F",
            "display_order": 1,
            "is_active": "on",
            "logo": uploaded_image("logo.png"),
        },
    )
    assert response.status_code == 302
    brand = Brand.objects.get(slug="lulu")
    assert brand.primary_color == "#F8C8DC"
    assert brand.logo.name.endswith(".webp")
    staff_client.post(
        url("brand_update", pk=brand.pk),
        {
            "name_en": "Lulu Pearl",
            "name_ar": "لولو",
            "slug": "lulu",
            "primary_color": "#F8C8DC",
            "secondary_color": "#9E526F",
            "display_order": 1,
        },
    )
    brand.refresh_from_db()
    assert brand.name_en == "Lulu Pearl" and brand.is_active is False
    staff_client.post(url("brand_delete", pk=brand.pk))
    assert not Brand.objects.filter(pk=brand.pk).exists()


def test_brand_colour_must_be_hex(staff_client, site_settings):
    response = staff_client.post(
        url("brand_create"),
        {
            "name_en": "X",
            "name_ar": "X",
            "slug": "x",
            "primary_color": "red;}body{display:none",
            "secondary_color": "#000000",
            "display_order": 0,
        },
    )
    assert response.status_code == 200
    assert "primary_color" in response.context["form"].errors


def test_brand_with_products_is_protected(staff_client, site_settings):
    product = make_product()
    response = staff_client.post(url("brand_delete", pk=product.brand.pk))
    assert response.status_code == 302
    assert Brand.objects.filter(pk=product.brand.pk).exists()


def test_staff_category_crud(staff_client, site_settings):
    staff_client.post(
        url("category_create"),
        {"name_en": "Rings", "name_ar": "خواتم", "slug": "rings", "display_order": 2, "is_active": "on"},
    )
    category = Category.objects.get(slug="rings")
    staff_client.post(
        url("category_update", pk=category.pk),
        {"name_en": "Rings", "name_ar": "خواتم", "slug": "rings-2", "display_order": 2},
    )
    category.refresh_from_db()
    assert category.slug == "rings-2"
    staff_client.post(url("category_delete", pk=category.pk))
    assert not Category.objects.filter(pk=category.pk).exists()


def product_payload(brand, category, **overrides):
    data = {
        "brand": brand.pk,
        "categories": [category.pk],
        "name_ar": "قرط",
        "name_en": "Earring",
        "slug": "earring",
        "sku": "EAR-1",
        "description_ar": "",
        "description_en": "",
        "regular_price": "49.90",
        "verification_status": "CONFIRMED",
        "is_active": "on",
        "variants-TOTAL_FORMS": "1",
        "variants-INITIAL_FORMS": "0",
        "variants-MIN_NUM_FORMS": "0",
        "variants-MAX_NUM_FORMS": "1000",
        "variants-0-name_ar": "ذهبي",
        "variants-0-name_en": "Gold",
        "variants-0-sku": "EAR-1-G",
        "variants-0-stock_quantity": "7",
        "variants-0-display_order": "0",
        "variants-0-is_active": "on",
        "variants-0-color_hex": "#c9a85c",
        "images-TOTAL_FORMS": "0",
        "images-INITIAL_FORMS": "0",
        "images-MIN_NUM_FORMS": "0",
        "images-MAX_NUM_FORMS": "1000",
    }
    data.update(overrides)
    return data


def test_staff_product_create_with_variants_and_images(staff_client, site_settings):
    brand, category = make_brand(), make_category()
    data = product_payload(brand, category)
    data["new_images"] = [uploaded_image("a.png"), uploaded_image("b.jpg", fmt="JPEG")]
    response = staff_client.post(url("product_create"), data)
    assert response.status_code == 302, response.context and response.context["form"].errors
    product = Product.objects.get(slug="earring")
    variant = product.variants.get()
    assert variant.stock_quantity == 7 and variant.color_hex == "#C9A85C"
    images = list(product.images.order_by("display_order"))
    assert len(images) == 2
    assert images[0].is_primary and not images[1].is_primary
    assert images[0].image.name.endswith(".webp") and images[0].thumbnail
    assert list(product.categories.all()) == [category]

    # Reorder and switch the primary image, then delete one image.
    edit = product_payload(
        brand,
        category,
        **{
            "variants-INITIAL_FORMS": "1",
            "variants-0-id": str(variant.pk),
            "images-TOTAL_FORMS": "2",
            "images-INITIAL_FORMS": "2",
            "images-0-id": str(images[0].pk),
            "images-0-display_order": "5",
            "images-0-DELETE": "on",
            "images-1-id": str(images[1].pk),
            "images-1-display_order": "1",
            "images-1-is_primary": "on",
        },
    )
    response = staff_client.post(url("product_update", pk=product.pk), edit)
    assert response.status_code == 302
    remaining = list(product.images.all())
    assert [image.pk for image in remaining] == [images[1].pk]
    assert remaining[0].is_primary


def test_product_needs_an_active_variant(staff_client, site_settings):
    data = product_payload(make_brand(), make_category(), **{"variants-TOTAL_FORMS": "0"})
    response = staff_client.post(url("product_create"), data)
    assert response.status_code == 200
    assert not Product.objects.exists()


@pytest.mark.parametrize(
    "bad_file",
    [
        SimpleUploadedFile("fake.png", b"this is not an image", content_type="image/png"),
        SimpleUploadedFile("vector.svg", b"<svg onload='alert(1)'></svg>", content_type="image/svg+xml"),
        SimpleUploadedFile("anim.gif", b"GIF89a\x01\x00\x01\x00\x00\x00\x00;", content_type="image/gif"),
    ],
)
def test_image_upload_validation_rejects_bad_files(staff_client, site_settings, bad_file):
    data = product_payload(make_brand(), make_category())
    data["new_images"] = [bad_file]
    response = staff_client.post(url("product_create"), data)
    assert response.status_code == 200
    assert "new_images" in response.context["form"].errors
    assert not ProductImage.objects.exists()


def test_image_upload_size_limit(staff_client, site_settings, settings):
    settings.MAX_IMAGE_UPLOAD_SIZE = 1024  # 1 KB for the test
    noisy = Image.frombytes("RGB", (200, 200), os.urandom(200 * 200 * 3))
    buffer = io.BytesIO()
    noisy.save(buffer, format="PNG")
    data = product_payload(make_brand(), make_category())
    data["new_images"] = [SimpleUploadedFile("big.png", buffer.getvalue(), content_type="image/png")]
    response = staff_client.post(url("product_create"), data)
    assert response.status_code == 200
    assert "new_images" in response.context["form"].errors


def test_uploaded_images_are_stripped_and_resized(site_settings, settings):
    settings.IMAGE_OPTIMIZE_MAX_EDGE = 200
    product = make_product()
    image = ProductImage.objects.create(product=product, image=uploaded_image("x.jpg", fmt="JPEG", size=(800, 400)))
    assert (image.width, image.height) == (200, 100)
    with image.image.open("rb") as handle, Image.open(handle) as stored:
        assert stored.format == "WEBP"
        assert not stored.getexif()


def test_staff_promotion_crud_and_validation(staff_client, site_settings):
    brand = make_brand()
    base = {
        "name_ar": "خصم",
        "name_en": "Sale",
        "discount_type": "PERCENTAGE",
        "value": "150",
        "scope": "BRAND",
        "brand": brand.pk,
        "starts_at": "2026-09-01T10:00",
        "priority": "0",
        "is_enabled": "on",
    }
    response = staff_client.post(url("promotion_create"), base)
    assert response.status_code == 200 and "value" in response.context["form"].errors
    base["value"] = "15"
    assert staff_client.post(url("promotion_create"), base).status_code == 302
    promotion = Promotion.objects.get()
    assert promotion.brand == brand and promotion.value == Decimal("15.00")
    staff_client.post(url("promotion_delete", pk=promotion.pk))
    assert not Promotion.objects.exists()


def test_stock_update_via_htmx(staff_client, site_settings):
    variant = make_product(stock=1).variants.first()
    response = staff_client.post(
        url("stock_update", pk=variant.pk), {"stock_quantity": "12"}, headers={"HX-Request": "true"}
    )
    assert response.status_code == 200 and f'id="stock-row-{variant.pk}"' in response.content.decode()
    variant.refresh_from_db()
    assert variant.stock_quantity == 12
    staff_client.post(url("stock_update", pk=variant.pk), {"stock_quantity": "-3"})
    variant.refresh_from_db()
    assert variant.stock_quantity == 12


def test_order_list_search_and_htmx(staff_client, site_settings):
    response = staff_client.get(
        url("order_list"), {"q": "RNQ"}, headers={"HX-Request": "true", "HX-Target": "order-results"}
    )
    assert response.status_code == 200
    assert "<html" not in response.content.decode()


def test_site_settings_update(staff_client, site_settings):
    data = {
        "store_name_ar": "رونق",
        "store_name_en": "Rawnaq Accessories",
        "whatsapp_number": "972553003327",
        "whatsapp_display_number": "0553003327",
        "instagram_url": "https://www.instagram.com/rawnaq_accessories1/",
        "default_delivery_fee": "25.00",
        "free_delivery_threshold": "200",
        "sale_banner_enabled": "on",
        "sale_banner_text_ar": "تخفيضات",
        "sale_banner_text_en": "Sale",
    }
    assert staff_client.post(url("settings"), data).status_code == 302
    site_settings.refresh_from_db()
    assert site_settings.default_delivery_fee == Decimal("25.00")
    data["whatsapp_number"] = "+972 55"
    response = staff_client.post(url("settings"), data)
    assert "whatsapp_number" in response.context["form"].errors


def test_django_admin_is_staff_only(client, customer_client, site_settings):
    assert client.get("/django-admin/").status_code == 302
    assert customer_client.get("/django-admin/").status_code == 302


def test_django_admin_pages_load_for_superuser(client, site_settings):
    from django.contrib import admin

    from conftest import make_user

    make_product()
    superuser = make_user(email="root@example.test", is_staff=True, is_superuser=True)
    client.force_login(superuser)
    assert "Rawnaq" in client.get("/django-admin/").content.decode()
    for model, model_admin in admin.site._registry.items():
        opts = model._meta
        changelist = f"/django-admin/{opts.app_label}/{opts.model_name}/"
        assert client.get(changelist).status_code == 200, changelist
        if model_admin.has_add_permission(type("R", (), {"user": superuser})()):
            assert client.get(changelist + "add/").status_code == 200, changelist
        first = model.objects.first()
        if first is not None:
            assert client.get(f"{changelist}{first.pk}/change/").status_code == 200, changelist
