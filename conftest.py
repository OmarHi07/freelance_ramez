"""Shared pytest fixtures and small factories (no extra factory library needed)."""

from __future__ import annotations

import io
from datetime import timedelta
from decimal import Decimal
from itertools import count

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image

from accounts.models import User
from catalog.models import (
    Brand,
    Category,
    DiscountType,
    Product,
    ProductVariant,
    Promotion,
    PromotionScope,
    VerificationStatus,
)
from core.models import SiteSettings

_seq = count(1)
PASSWORD = "a-Secure-pass-2026!"


def image_bytes(fmt: str = "PNG", size=(64, 64), color=(248, 200, 220)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def uploaded_image(name: str = "photo.png", fmt: str = "PNG", **kwargs) -> SimpleUploadedFile:
    content_type = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[fmt]
    return SimpleUploadedFile(name, image_bytes(fmt, **kwargs), content_type=content_type)


@pytest.fixture
def site_settings(db):
    obj = SiteSettings.load()
    obj.default_delivery_fee = Decimal("20.00")
    obj.free_delivery_threshold = None
    obj.save()
    return obj


def make_brand(**kwargs) -> Brand:
    n = next(_seq)
    defaults = {
        "name_en": f"Brand {n}",
        "name_ar": f"ماركة {n}",
        "slug": f"brand-{n}",
        "primary_color": "#F8C8DC",
        "secondary_color": "#9E526F",
    }
    defaults.update(kwargs)
    return Brand.objects.create(**defaults)


def make_category(**kwargs) -> Category:
    n = next(_seq)
    defaults = {"name_en": f"Category {n}", "name_ar": f"فئة {n}", "slug": f"category-{n}"}
    defaults.update(kwargs)
    return Category.objects.create(**defaults)


def make_product(brand=None, *, price="100.00", stock=10, categories=(), variants=1, **kwargs) -> Product:
    n = next(_seq)
    brand = brand or make_brand()
    defaults = {
        "brand": brand,
        "name_en": f"Product {n}",
        "name_ar": f"منتج {n}",
        "slug": f"product-{n}",
        "sku": f"SKU-{n}",
        "regular_price": Decimal(price),
        "verification_status": VerificationStatus.CONFIRMED,
    }
    defaults.update(kwargs)
    product = Product.objects.create(**defaults)
    if categories:
        product.categories.set(categories)
    for index in range(variants):
        ProductVariant.objects.create(
            product=product,
            name_en=f"Option {index + 1}",
            name_ar=f"خيار {index + 1}",
            sku=f"{defaults['sku']}-{index + 1}",
            stock_quantity=stock,
        )
    return product


def make_promotion(
    *, scope=PromotionScope.STORE, discount_type=DiscountType.PERCENTAGE, value="10.00", starts=-1, ends=30, **kwargs
) -> Promotion:
    now = timezone.now()
    n = next(_seq)
    return Promotion.objects.create(
        name_en=f"Promo {n}",
        name_ar=f"عرض {n}",
        scope=scope,
        discount_type=discount_type,
        value=Decimal(value),
        starts_at=now + timedelta(days=starts),
        ends_at=None if ends is None else now + timedelta(days=ends),
        **kwargs,
    )


def make_user(email=None, **kwargs) -> User:
    n = next(_seq)
    email = email or f"customer{n}@example.test"
    kwargs.setdefault("full_name", f"Customer {n}")
    kwargs.setdefault("phone", "0501234567")
    return User.objects.create_user(email=email, password=PASSWORD, **kwargs)


@pytest.fixture
def customer(db):
    return make_user()


@pytest.fixture
def other_customer(db):
    return make_user()


@pytest.fixture
def staff_user(db):
    return make_user(email="owner@example.test", is_staff=True)


@pytest.fixture
def customer_client(client, customer):
    client.force_login(customer)
    return client


@pytest.fixture
def staff_client(client, staff_user):
    client.force_login(staff_user)
    return client
