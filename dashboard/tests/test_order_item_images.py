"""Owner order detail shows a thumbnail for every ordered item."""

import re
from decimal import Decimal

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation

from catalog.models import ProductImage
from conftest import make_product, uploaded_image
from orders.models import Order, OrderItem

pytestmark = pytest.mark.django_db

PLACEHOLDER = "placeholder-product.svg"


def url(name, lang="en", **kwargs):
    with translation.override(lang):
        return reverse(name, kwargs=kwargs or None)


def make_order(customer, **kwargs) -> Order:
    defaults = {
        "customer": customer,
        "number": f"RNQ-20260927-{Order.objects.count():04d}",
        "customer_name": customer.full_name,
        "customer_email": customer.email,
        "customer_phone": "0553003327",
        "city": "Haifa",
        "street": "HaGefen",
        "building_number": "12",
        "subtotal": Decimal("0.00"),
        "discount_total": Decimal("0.00"),
        "delivery_fee": Decimal("0.00"),
        "total": Decimal("0.00"),
        "language": "en",
    }
    defaults.update(kwargs)
    return Order.objects.create(**defaults)


def add_item(order, product, quantity=1, price="50.00") -> OrderItem:
    variant = product.variants.first()
    unit = Decimal(price)
    item = OrderItem.objects.create(
        order=order,
        product=product,
        variant=variant,
        product_name_ar=product.name_ar,
        product_name_en=product.name_en,
        variant_name_ar=variant.name_ar if variant else "",
        variant_name_en=variant.name_en if variant else "",
        brand_name=product.brand.name_en,
        sku=variant.sku if variant else product.sku,
        quantity=quantity,
        original_unit_price=unit,
        unit_discount=Decimal("0.00"),
        final_unit_price=unit,
        line_total=unit * quantity,
    )
    Order.objects.filter(pk=order.pk).update(
        subtotal=order.subtotal + item.line_total, total=order.total + item.line_total
    )
    order.refresh_from_db()
    return item


def detail_html(client, order) -> str:
    response = client.get(url("dashboard:order_detail", pk=order.pk))
    assert response.status_code == 200
    return response.content.decode()


def item_cell(html: str, product_name: str) -> str:
    """The single <td> block that holds this product's name and thumbnail."""
    cells = re.findall(r'<td data-label="Product">(.*?)</td>', html, re.S)
    matching = [cell for cell in cells if product_name in cell]
    assert matching, f"no product cell found for {product_name!r}"
    return matching[0]


def image_sources(fragment: str) -> list[str]:
    return re.findall(r'<img[^>]*\ssrc="([^"]+)"', fragment)


# ---------------------------------------------------------------------------
# The thumbnail itself
# ---------------------------------------------------------------------------
def test_owner_sees_the_thumbnail_for_an_imaged_product(staff_client, customer, site_settings):
    product = make_product()
    image = ProductImage.objects.create(product=product, image=uploaded_image("p.png", size=(800, 800)))
    order = make_order(customer)
    add_item(order, product)

    cell = item_cell(detail_html(staff_client, order), product.name_en)
    sources = image_sources(cell)
    assert sources == [image.thumbnail.url], sources
    # The stored thumbnail, not the full-resolution file.
    assert image.thumbnail.url != image.image.url
    assert PLACEHOLDER not in cell


def test_the_thumbnail_carries_the_product_name_size_and_lazy_loading(staff_client, customer, site_settings):
    product = make_product()
    ProductImage.objects.create(product=product, image=uploaded_image("p.png", size=(800, 800)))
    order = make_order(customer)
    add_item(order, product)

    cell = item_cell(detail_html(staff_client, order), product.name_en)
    tag = re.search(r"<img[^>]*>", cell).group(0)
    assert f'alt="{product.name_en}"' in tag
    assert 'width="96"' in tag and 'height="96"' in tag
    assert 'loading="lazy"' in tag


def test_the_thumbnail_links_to_the_full_picture_in_a_new_tab(staff_client, customer, site_settings):
    product = make_product()
    image = ProductImage.objects.create(product=product, image=uploaded_image("p.png", size=(800, 800)))
    order = make_order(customer)
    add_item(order, product)

    cell = item_cell(detail_html(staff_client, order), product.name_en)
    link = re.search(r'<a class="order-item__thumb"[^>]*>', cell).group(0)
    assert f'href="{image.image.url}"' in link
    assert 'target="_blank"' in link
    assert 'rel="noopener noreferrer"' in link


def test_the_page_never_exposes_a_server_filesystem_path(staff_client, customer, site_settings):
    product = make_product()
    ProductImage.objects.create(product=product, image=uploaded_image("p.png", size=(800, 800)))
    order = make_order(customer)
    add_item(order, product)

    html = detail_html(staff_client, order)
    for source in image_sources(html):
        assert not re.match(r"^[A-Za-z]:[\\/]", source), source  # no C:\...
        assert "\\" not in source
        assert source.startswith(("/", "http://", "https://"))


# ---------------------------------------------------------------------------
# Which image is chosen
# ---------------------------------------------------------------------------
def test_the_primary_image_wins_over_the_other_product_images(staff_client, customer, site_settings):
    product = make_product()
    first = ProductImage.objects.create(
        product=product, image=uploaded_image("a.png", size=(800, 800)), display_order=1, is_primary=False
    )
    primary = ProductImage.objects.create(
        product=product, image=uploaded_image("b.png", size=(800, 800)), display_order=2, is_primary=True
    )
    order = make_order(customer)
    item = add_item(order, product)

    assert item.display_image == primary
    cell = item_cell(detail_html(staff_client, order), product.name_en)
    assert primary.thumbnail.url in cell
    assert first.thumbnail.url not in cell


def test_the_first_image_is_used_when_none_is_marked_primary(staff_client, customer, site_settings):
    product = make_product()
    first = ProductImage.objects.create(
        product=product, image=uploaded_image("a.png", size=(800, 800)), display_order=1, is_primary=False
    )
    ProductImage.objects.create(
        product=product, image=uploaded_image("b.png", size=(800, 800)), display_order=2, is_primary=False
    )
    order = make_order(customer)
    item = add_item(order, product)

    assert item.display_image == first
    assert first.thumbnail.url in item_cell(detail_html(staff_client, order), product.name_en)


def test_variants_have_no_images_so_the_product_image_is_used(staff_client, customer, site_settings):
    """Documents why the variant step of the priority list is a no-op here.

    If variants ever gain their own picture, ``OrderItem.display_image`` is the
    single place that has to prefer it.
    """
    from catalog.models import ProductVariant

    assert not [field.name for field in ProductVariant._meta.get_fields() if field.get_internal_type() == "ImageField"]
    assert not [field.name for field in OrderItem._meta.get_fields() if field.get_internal_type() == "ImageField"]

    product = make_product()
    image = ProductImage.objects.create(product=product, image=uploaded_image("p.png", size=(800, 800)))
    order = make_order(customer)
    item = add_item(order, product)
    assert item.variant is not None
    assert item.display_image == image


# ---------------------------------------------------------------------------
# Fallbacks never break the page
# ---------------------------------------------------------------------------
def test_a_product_without_an_image_shows_the_placeholder(staff_client, customer, site_settings):
    product = make_product()
    order = make_order(customer)
    item = add_item(order, product)

    assert item.display_image is None
    cell = item_cell(detail_html(staff_client, order), product.name_en)
    assert PLACEHOLDER in cell
    assert "No image" in cell
    # No dead link wrapped around the placeholder.
    assert '<a class="order-item__thumb"' not in cell


def test_a_deleted_product_still_renders_the_line(staff_client, customer, site_settings):
    product = make_product()
    ProductImage.objects.create(product=product, image=uploaded_image("p.png", size=(800, 800)))
    order = make_order(customer)
    item = add_item(order, product)
    name = product.name_en

    product.variants.all().delete()
    product.delete()  # product FK is SET_NULL; the snapshot stays on the item
    item.refresh_from_db()
    assert item.product is None
    assert item.display_image is None

    cell = item_cell(detail_html(staff_client, order), name)
    assert PLACEHOLDER in cell
    assert name in cell  # the snapshot name survives


def test_an_image_row_whose_file_reference_was_lost_does_not_crash(staff_client, customer, site_settings):
    product = make_product()
    image = ProductImage.objects.create(product=product, image=uploaded_image("p.png", size=(800, 800)))
    # Simulate a broken row without touching storage, so this holds on S3 too.
    ProductImage.objects.filter(pk=image.pk).update(image="", thumbnail="")
    order = make_order(customer)
    item = add_item(order, product)
    item.refresh_from_db()

    assert item.display_image is None
    cell = item_cell(detail_html(staff_client, order), product.name_en)
    assert PLACEHOLDER in cell


def test_a_file_missing_from_storage_still_renders(staff_client, customer, site_settings):
    """The row is intact, so a URL is emitted; only the browser sees it 404."""
    from django.core.files.storage import default_storage

    product = make_product()
    image = ProductImage.objects.create(product=product, image=uploaded_image("p.png", size=(800, 800)))
    order = make_order(customer)
    add_item(order, product)

    default_storage.delete(image.image.name)
    default_storage.delete(image.thumbnail.name)

    cell = item_cell(detail_html(staff_client, order), product.name_en)
    assert image.thumbnail.url in cell


# ---------------------------------------------------------------------------
# Several items, both languages
# ---------------------------------------------------------------------------
def test_each_item_shows_its_own_image(staff_client, customer, site_settings):
    with_image = make_product()
    first = ProductImage.objects.create(product=with_image, image=uploaded_image("a.png", size=(800, 800)))
    other = make_product()
    second = ProductImage.objects.create(product=other, image=uploaded_image("b.png", size=(800, 800)))
    without = make_product()

    order = make_order(customer)
    add_item(order, with_image, quantity=2)
    add_item(order, other, quantity=3)
    add_item(order, without, quantity=1)

    html = detail_html(staff_client, order)
    assert first.thumbnail.url in item_cell(html, with_image.name_en)
    assert second.thumbnail.url in item_cell(html, other.name_en)
    assert PLACEHOLDER in item_cell(html, without.name_en)
    # Each thumbnail belongs to exactly one line.
    assert first.thumbnail.url not in item_cell(html, other.name_en)
    assert html.count('class="order-item"') == 3


@pytest.mark.parametrize("lang", ["en", "ar"])
def test_both_languages_render_the_item_with_its_image_option_and_quantity(staff_client, customer, site_settings, lang):
    product = make_product()
    image = ProductImage.objects.create(product=product, image=uploaded_image("p.png", size=(800, 800)))
    order = make_order(customer)
    item = add_item(order, product, quantity=4)

    response = staff_client.get(url("dashboard:order_detail", lang=lang, pk=order.pk))
    assert response.status_code == 200
    html = response.content.decode()

    expected_name = product.name_ar if lang == "ar" else product.name_en
    cell = item_cell(html, expected_name) if lang == "en" else html
    assert image.thumbnail.url in cell
    assert expected_name in html
    assert (item.variant_name_ar if lang == "ar" else item.variant_name_en) in html
    assert ">4<" in html or "4" in html  # quantity
    assert item.sku in html
    assert f'dir="{"rtl" if lang == "ar" else "ltr"}"' in html


def test_arabic_page_uses_the_arabic_product_name_as_alt_text(staff_client, customer, site_settings):
    product = make_product()
    ProductImage.objects.create(product=product, image=uploaded_image("p.png", size=(800, 800)))
    order = make_order(customer)
    add_item(order, product)

    html = staff_client.get(url("dashboard:order_detail", lang="ar", pk=order.pk)).content.decode()
    assert f'alt="{product.name_ar}"' in html


# ---------------------------------------------------------------------------
# Access control and query count
# ---------------------------------------------------------------------------
def test_anonymous_and_customers_still_cannot_open_the_page(client, customer, other_customer, site_settings):
    product = make_product()
    ProductImage.objects.create(product=product, image=uploaded_image("p.png", size=(800, 800)))
    order = make_order(customer)
    add_item(order, product)
    target = url("dashboard:order_detail", pk=order.pk)

    response = client.get(target)
    assert response.status_code == 302 and "/account/login/" in response["Location"]

    client.force_login(customer)  # the order's own customer is still not staff
    assert client.get(target).status_code == 403
    client.force_login(other_customer)
    assert client.get(target).status_code == 403


def queries_to_open(staff_user, order) -> int:
    session = Client()
    session.force_login(staff_user)
    with CaptureQueriesContext(connection) as captured:
        assert session.get(url("dashboard:order_detail", pk=order.pk)).status_code == 200
    return len(captured.captured_queries)


def test_the_thumbnails_do_not_add_a_query_per_item(staff_user, customer, site_settings):
    """The query count must not grow with the number of lines."""
    small = make_order(customer)
    for _ in range(2):
        product = make_product()
        ProductImage.objects.create(product=product, image=uploaded_image("p.png", size=(800, 800)))
        add_item(small, product)
    baseline = queries_to_open(staff_user, small)

    bigger = make_order(customer, number="RNQ-20260927-BIG1")
    for _ in range(10):
        product = make_product()
        ProductImage.objects.create(product=product, image=uploaded_image("p.png", size=(800, 800)))
        add_item(bigger, product)
    grown = queries_to_open(staff_user, bigger)

    # 2 lines -> 12 lines. One query per line would add at least ten.
    assert grown == baseline, f"{baseline} queries for 2 items but {grown} for 12"
