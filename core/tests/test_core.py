import re
from pathlib import Path

import environ
import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.template import engines
from django.template.loader import get_template
from django.urls import reverse
from django.utils import translation

from accounts.models import User
from catalog.models import Brand, Product, ProductImage, Promotion
from config.storage import build_media_storage
from conftest import make_brand, make_product
from core.formatting import format_money

pytestmark = pytest.mark.django_db


def test_health_check(client):
    response = client.get("/healthz/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_security_headers(client, site_settings):
    response = client.get("/en/")
    assert response["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response["Content-Security-Policy"]
    assert "script-src 'self'" in response["Content-Security-Policy"]
    assert "geolocation=(self)" in response["Permissions-Policy"]
    assert response["X-Content-Type-Options"] == "nosniff"


def test_pages_have_no_inline_scripts(client, site_settings):
    make_product(make_brand())
    for path in ("/ar/", "/en/brands/", "/en/cart/", "/en/account/login/"):
        html = client.get(path).content.decode()
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), path
        assert "onclick=" not in html and "onload=" not in html


@pytest.mark.parametrize(
    ("lang", "direction", "text"), [("ar", "rtl", "تسوّقي حسب الماركة"), ("en", "ltr", "Shop by brand")]
)
def test_arabic_and_english_pages_render(client, site_settings, lang, direction, text):
    response = client.get(f"/{lang}/")
    html = response.content.decode()
    assert response.status_code == 200
    assert f'<html lang="{lang}" dir="{direction}">' in html
    assert text in html


def test_root_redirects_to_arabic_by_default(client):
    response = client.get("/", headers={"Accept-Language": ""})
    assert response.status_code == 302 and response["Location"] == "/ar/"


def test_language_switch_preserves_current_page(client, site_settings):
    brand = make_brand()
    response = client.post("/i18n/setlang/", {"language": "en", "next": f"/ar/brands/{brand.slug}/?sort=price_asc"})
    assert response.status_code == 302
    assert response["Location"] == f"/en/brands/{brand.slug}/?sort=price_asc"


def test_database_content_is_localized(client, site_settings):
    product = make_product(name_en="Pearl Drop", name_ar="قرط لؤلؤ")
    assert "قرط لؤلؤ" in client.get(f"/ar/products/{product.slug}/").content.decode()
    english = client.get(f"/en/products/{product.slug}/").content.decode()
    assert "Pearl Drop" in english
    with translation.override("ar"):
        assert product.name == "قرط لؤلؤ"


def test_branded_404(client, site_settings):
    response = client.get("/en/definitely-missing/")
    assert response.status_code == 404
    assert "We couldn’t find that page" in response.content.decode()


def test_all_templates_compile():
    template_dirs = [Path(settings.BASE_DIR) / "templates"]
    names = []
    for directory in template_dirs:
        names += [str(path.relative_to(directory)) for path in directory.rglob("*") if path.suffix in {".html", ".txt"}]
    assert len(names) > 40
    for name in names:
        get_template(name)
    assert engines["django"]


def test_static_assets_referenced_by_templates_exist():
    static_root = Path(settings.BASE_DIR) / "static"
    pattern = re.compile(r"""{%\s*static\s+['"]([^'"]+)['"]\s*%}""")
    missing = []
    for template in (Path(settings.BASE_DIR) / "templates").rglob("*.html"):
        for asset in pattern.findall(template.read_text(encoding="utf-8")):
            if not (static_root / asset).exists():
                missing.append(f"{template.name}: {asset}")
    css = (static_root / "css" / "fonts.css").read_text()
    for font in re.findall(r'url\("\.\./([^"]+)"\)', css):
        if not (static_root / font).exists():
            missing.append(f"fonts.css: {font}")
    assert not missing


def test_money_formatting():
    assert format_money("1234.5") == "₪1,234.50"
    assert format_money(0) == "₪0.00"


def test_media_storage_configuration(monkeypatch):
    env = environ.Env()
    monkeypatch.setenv("MEDIA_STORAGE_BACKEND", "local")
    assert build_media_storage(env)["BACKEND"].endswith("FileSystemStorage")
    monkeypatch.setenv("MEDIA_STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET_NAME", "rawnaq-media")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://example.r2.cloudflarestorage.com")
    config = build_media_storage(env)
    assert config["BACKEND"] == "storages.backends.s3.S3Storage"
    assert config["OPTIONS"]["bucket_name"] == "rawnaq-media" and config["OPTIONS"]["file_overwrite"] is False
    monkeypatch.setenv("MEDIA_STORAGE_BACKEND", "cloudinary")
    monkeypatch.delenv("CLOUDINARY_URL", raising=False)
    with pytest.raises(ImproperlyConfigured):
        build_media_storage(env)
    monkeypatch.setenv("MEDIA_STORAGE_BACKEND", "ftp")
    with pytest.raises(ImproperlyConfigured):
        build_media_storage(env)


def test_seed_demo_is_idempotent_and_creates_no_users(site_settings):
    call_command("seed_demo", verbosity=0)
    counts = (Brand.objects.count(), Product.objects.count(), ProductImage.objects.count(), Promotion.objects.count())
    call_command("seed_demo", verbosity=0)
    assert counts == (
        Brand.objects.count(),
        Product.objects.count(),
        ProductImage.objects.count(),
        Promotion.objects.count(),
    )
    assert counts[0] >= 3 and counts[1] == 12 and counts[3] == 3
    assert set(Promotion.objects.values_list("scope", flat=True)) == {"PRODUCT", "BRAND", "STORE"}
    assert not User.objects.exists()


def test_robots_txt_hides_private_areas(client):
    body = client.get("/robots.txt").content.decode()
    assert "Disallow: /owner/" in body and "Disallow: /django-admin/" in body


def test_csrf_protection_is_enforced(site_settings):
    from django.test import Client

    strict = Client(enforce_csrf_checks=True)
    variant = make_product().variants.first()
    with translation.override("en"):
        response = strict.post(reverse("cart:add"), {"variant": variant.pk, "quantity": 1})
    assert response.status_code == 403


def test_health_check_works_for_internal_host_names(client):
    response = client.get("/healthz/", headers={"Host": "10.0.0.12:8000"})
    assert response.status_code == 200 and response["Cache-Control"] == "no-store"
    assert client.get("/en/", headers={"Host": "evil.example.com"}).status_code == 400
