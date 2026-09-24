"""Idempotent demo data: ``python manage.py seed_demo``.

Creates editable demo brands, categories, ~12 products with variants and
original placeholder images, plus three promotions (product, brand and
store-wide). Running it again updates the same rows instead of duplicating
them. It never creates user accounts or passwords.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from catalog.models import (
    Brand,
    Category,
    DiscountType,
    Product,
    ProductImage,
    ProductVariant,
    Promotion,
    PromotionScope,
    VerificationStatus,
)
from core.models import SiteSettings

ASSETS = Path(__file__).resolve().parents[2] / "demo_assets"

BRANDS = [
    # slug, name_en, name_ar, primary, secondary, order
    ("lulu-pearl", "Lulu Pearl", "لولو بيرل", "#F8C8DC", "#9E526F", 1),
    ("rose-atelier", "Rose Atelier", "روز أتيليه", "#F6DCCB", "#8C4B3E", 2),
    ("luna-charm", "Luna Charm", "لونا تشارم", "#DCD3F5", "#5B4A9E", 3),
    ("mint-bow", "Mint Bow", "مِنت بو", "#CDEBDF", "#2F6B55", 4),
]

CATEGORIES = [
    ("earrings", "Earrings", "أقراط", 1),
    ("necklaces", "Necklaces", "قلائد", 2),
    ("bracelets", "Bracelets", "أساور", 3),
    ("rings", "Rings", "خواتم", 4),
    ("hair-accessories", "Hair accessories", "إكسسوارات الشعر", 5),
]

GOLD = ("Gold tone", "لون ذهبي", "#C9A85C")
SILVER = ("Silver tone", "لون فضي", "#C0C4CC")

PRODUCTS = [
    {
        "slug": "pearl-drop-earrings",
        "brand": "lulu-pearl",
        "categories": ["earrings"],
        "en": "Pearl Drop Earrings",
        "ar": "أقراط اللؤلؤ المتدلية",
        "sku": "LP-EAR-001",
        "price": "59.90",
        "status": VerificationStatus.CONFIRMED,
        "featured": True,
        "desc_en": "Soft faux-pearl drops on a light hook. Easy to wear every day.",
        "desc_ar": "أقراط لؤلؤ صناعي ناعمة بخطّاف خفيف، مناسبة للاستخدام اليومي.",
        "variants": [(GOLD, 8, None), (SILVER, 5, None)],
    },
    {
        "slug": "pearl-hair-clip-set",
        "brand": "lulu-pearl",
        "categories": ["hair-accessories"],
        "en": "Pearl Hair Clip Set",
        "ar": "طقم مشابك شعر باللؤلؤ",
        "sku": "LP-HAIR-002",
        "price": "39.90",
        "status": VerificationStatus.CONFIRMED,
        "featured": False,
        "desc_en": "A set of three pearl snap clips for braids and half-up styles.",
        "desc_ar": "طقم من ثلاثة مشابك باللؤلؤ للضفائر وتسريحات نصف مرفوعة.",
        "variants": [(("Standard", "قياسي", ""), 12, None)],
    },
    {
        "slug": "mini-pearl-necklace",
        "brand": "lulu-pearl",
        "categories": ["necklaces"],
        "en": "Mini Pearl Necklace",
        "ar": "قلادة اللؤلؤ الصغيرة",
        "sku": "LP-NCK-003",
        "price": "79.00",
        "status": VerificationStatus.UNKNOWN,
        "featured": True,
        "desc_en": "A delicate chain with small pearls and an adjustable clasp.",
        "desc_ar": "سلسلة رقيقة بحبّات لؤلؤ صغيرة وقفل قابل للتعديل.",
        "variants": [(GOLD, 3, None), (SILVER, 0, None)],
    },
    {
        "slug": "satin-scrunchie-trio",
        "brand": "rose-atelier",
        "categories": ["hair-accessories"],
        "en": "Satin Scrunchie Trio",
        "ar": "ثلاث ربطات شعر من الساتان",
        "sku": "RA-HAIR-001",
        "price": "29.90",
        "status": VerificationStatus.NOT_CONFIRMED,
        "featured": False,
        "desc_en": "Three gentle satin scrunchies that are kind to hair.",
        "desc_ar": "ثلاث ربطات ساتان لطيفة على الشعر.",
        "variants": [
            (("Blush", "وردي فاتح", "#E8A7A0"), 15, None),
            (("Champagne", "شامبين", "#E9D4B5"), 9, None),
            (("Mauve", "موف", "#B07A8C"), 2, None),
        ],
    },
    {
        "slug": "rose-charm-bracelet",
        "brand": "rose-atelier",
        "categories": ["bracelets"],
        "en": "Rose Charm Bracelet",
        "ar": "سوار بتعليقة وردة",
        "sku": "RA-BRC-002",
        "price": "49.00",
        "status": VerificationStatus.CONFIRMED,
        "featured": True,
        "desc_en": "Beaded bracelet with a small rose charm.",
        "desc_ar": "سوار من الخرز مع تعليقة وردة صغيرة.",
        "variants": [(("Standard", "قياسي", ""), 7, None)],
    },
    {
        "slug": "heart-stud-earrings",
        "brand": "rose-atelier",
        "categories": ["earrings"],
        "en": "Heart Stud Earrings",
        "ar": "أقراط على شكل قلب",
        "sku": "RA-EAR-003",
        "price": "35.00",
        "status": VerificationStatus.UNKNOWN,
        "featured": False,
        "desc_en": "Tiny enamel hearts with comfortable backs.",
        "desc_ar": "قلوب صغيرة بالمينا مع مشابك خلفية مريحة.",
        "variants": [(("Rose", "وردي", "#D9757F"), 10, None), (GOLD, 4, None)],
    },
    {
        "slug": "crescent-moon-necklace",
        "brand": "luna-charm",
        "categories": ["necklaces"],
        "en": "Crescent Moon Necklace",
        "ar": "قلادة الهلال",
        "sku": "LC-NCK-001",
        "price": "69.00",
        "status": VerificationStatus.CONFIRMED,
        "featured": True,
        "desc_en": "A crescent pendant with tiny sparkling stars.",
        "desc_ar": "قلادة على شكل هلال مع نجوم صغيرة لامعة.",
        "variants": [(GOLD, 6, None), (SILVER, 6, None)],
    },
    {
        "slug": "star-stacking-rings",
        "brand": "luna-charm",
        "categories": ["rings"],
        "en": "Star Stacking Rings",
        "ar": "خواتم النجوم المتراكبة",
        "sku": "LC-RNG-002",
        "price": "45.00",
        "status": VerificationStatus.NOT_CONFIRMED,
        "featured": False,
        "desc_en": "Two slim rings to wear together or apart.",
        "desc_ar": "خاتمان رفيعان يمكن ارتداؤهما معًا أو كلّ على حدة.",
        "variants": [(("Size S", "مقاس S", ""), 5, None), (("Size M", "مقاس M", ""), 3, None)],
    },
    {
        "slug": "lavender-bead-bracelet",
        "brand": "luna-charm",
        "categories": ["bracelets"],
        "en": "Lavender Bead Bracelet",
        "ar": "سوار خرز بلون اللافندر",
        "sku": "LC-BRC-003",
        "price": "32.00",
        "status": VerificationStatus.UNKNOWN,
        "featured": False,
        "desc_en": "Stretchy bracelet with lavender and pearl-white beads.",
        "desc_ar": "سوار مطاطي بخرز بلون اللافندر والأبيض اللؤلؤي.",
        "variants": [(("Standard", "قياسي", ""), 14, None)],
    },
    {
        "slug": "velvet-bow-barrette",
        "brand": "mint-bow",
        "categories": ["hair-accessories"],
        "en": "Velvet Bow Barrette",
        "ar": "مشبك شعر بفيونكة مخملية",
        "sku": "MB-HAIR-001",
        "price": "27.50",
        "status": VerificationStatus.CONFIRMED,
        "featured": True,
        "desc_en": "A soft velvet bow on a secure barrette.",
        "desc_ar": "فيونكة مخملية ناعمة على مشبك ثابت.",
        "variants": [
            (("Mint", "نعناعي", "#3F8C70"), 11, None),
            (("Black", "أسود", "#222222"), 8, None),
            (("Cream", "كريمي", "#F1E6D2"), 1, None),
        ],
    },
    {
        "slug": "daisy-hoop-earrings",
        "brand": "mint-bow",
        "categories": ["earrings"],
        "en": "Daisy Hoop Earrings",
        "ar": "أقراط حلقية بزهرة الأقحوان",
        "sku": "MB-EAR-002",
        "price": "42.00",
        "status": VerificationStatus.UNKNOWN,
        "featured": False,
        "desc_en": "Small hoops with removable daisy charms.",
        "desc_ar": "حلقات صغيرة مع تعليقات أقحوان قابلة للإزالة.",
        "variants": [(GOLD, 6, None)],
    },
    {
        "slug": "enamel-flower-ring",
        "brand": "mint-bow",
        "categories": ["rings"],
        "en": "Enamel Flower Ring",
        "ar": "خاتم زهرة بالمينا",
        "sku": "MB-RNG-003",
        "price": "38.00",
        "status": VerificationStatus.NOT_CONFIRMED,
        "featured": False,
        "desc_en": "Adjustable ring with a pink enamel flower.",
        "desc_ar": "خاتم قابل للتعديل مع زهرة وردية بالمينا.",
        "variants": [
            (("Adjustable", "قابل للتعديل", ""), 9, None),
            (("Large flower", "زهرة كبيرة", "#F29BB0"), 4, "42.00"),
        ],
    },
]


class Command(BaseCommand):
    help = "Create or update demo catalogue data (safe to run repeatedly). Does not create any user accounts."

    @transaction.atomic
    def handle(self, *args, **options):
        settings_obj = SiteSettings.load()
        if not settings_obj.sale_banner_text_en and not settings_obj.sale_banner_text_ar:
            settings_obj.sale_banner_text_en = "Welcome offer: 10% off the whole store this month."
            settings_obj.sale_banner_text_ar = "عرض الترحيب: خصم 10% على المتجر بالكامل هذا الشهر."
            settings_obj.sale_banner_enabled = True
        if not settings_obj.delivery_notice_en and not settings_obj.delivery_notice_ar:
            settings_obj.delivery_notice_en = "Delivery details and timing are confirmed with you on WhatsApp."
            settings_obj.delivery_notice_ar = "نؤكّد معك تفاصيل التوصيل وموعده عبر واتساب."
        settings_obj.save()

        brands = {}
        for slug, name_en, name_ar, primary, secondary, order in BRANDS:
            brand, _ = Brand.objects.update_or_create(
                slug=slug,
                defaults={
                    "name_en": name_en,
                    "name_ar": name_ar,
                    "primary_color": primary,
                    "secondary_color": secondary,
                    "display_order": order,
                    "is_active": True,
                },
            )
            if not brand.logo:
                brand.logo.save(f"{slug}.webp", self._asset(f"brand-{slug}.webp"), save=True)
            brands[slug] = brand

        categories = {}
        for slug, name_en, name_ar, order in CATEGORIES:
            categories[slug], _ = Category.objects.update_or_create(
                slug=slug, defaults={"name_en": name_en, "name_ar": name_ar, "display_order": order, "is_active": True}
            )

        now = timezone.now()
        products = {}
        for index, data in enumerate(PRODUCTS):
            product, _ = Product.objects.update_or_create(
                slug=data["slug"],
                defaults={
                    "brand": brands[data["brand"]],
                    "name_en": data["en"],
                    "name_ar": data["ar"],
                    "sku": data["sku"],
                    "regular_price": Decimal(data["price"]),
                    "description_en": data["desc_en"],
                    "description_ar": data["desc_ar"],
                    "verification_status": data["status"],
                    "is_featured": data["featured"],
                    "is_active": True,
                },
            )
            # Spread creation dates so "newest" sorting is meaningful.
            Product.objects.filter(pk=product.pk).update(created_at=now - timedelta(days=len(PRODUCTS) - index))
            product.categories.set([categories[slug] for slug in data["categories"]])
            for order, ((name_en, name_ar, color_hex), stock, override) in enumerate(data["variants"]):
                ProductVariant.objects.update_or_create(
                    sku=f"{data['sku']}-{order + 1:02d}",
                    defaults={
                        "product": product,
                        "name_en": name_en,
                        "name_ar": name_ar,
                        "color_name_en": name_en if color_hex else "",
                        "color_name_ar": name_ar if color_hex else "",
                        "color_hex": color_hex,
                        "stock_quantity": stock,
                        "price_override": Decimal(override) if override else None,
                        "display_order": order,
                        "is_active": True,
                    },
                )
            if not product.images.exists():
                for number in (1, 2):
                    ProductImage.objects.create(
                        product=product,
                        image=self._asset(f"{data['slug']}-{number}.webp", name=f"{data['slug']}-{number}.webp"),
                        alt_text_en=f"{data['en']} — illustration {number}",
                        alt_text_ar=f"{data['ar']} — صورة توضيحية {number}",
                        display_order=number,
                        is_primary=number == 1,
                    )
            products[data["slug"]] = product

        start = now - timedelta(days=1)
        end = now + timedelta(days=30)
        promotions = [
            (
                "Pearl drop 20% off",
                "خصم 20% على أقراط اللؤلؤ",
                DiscountType.PERCENTAGE,
                "20.00",
                PromotionScope.PRODUCT,
                {"product": products["pearl-drop-earrings"]},
            ),
            (
                "Luna Charm ₪10 off",
                "خصم 10 ₪ على لونا تشارم",
                DiscountType.FIXED,
                "10.00",
                PromotionScope.BRAND,
                {"brand": brands["luna-charm"]},
            ),
            ("Welcome offer 10%", "عرض الترحيب 10%", DiscountType.PERCENTAGE, "10.00", PromotionScope.STORE, {}),
        ]
        for name_en, name_ar, discount_type, value, scope, target in promotions:
            Promotion.objects.update_or_create(
                name_en=name_en,
                defaults={
                    "name_ar": name_ar,
                    "discount_type": discount_type,
                    "value": Decimal(value),
                    "scope": scope,
                    "brand": target.get("brand"),
                    "category": target.get("category"),
                    "product": target.get("product"),
                    "starts_at": start,
                    "ends_at": end,
                    "is_enabled": True,
                    "priority": 0,
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo data ready: {len(brands)} brands, {len(categories)} categories, "
                f"{len(products)} products, {len(promotions)} promotions."
            )
        )
        self.stdout.write("No user accounts were created. Create the owner with: python manage.py createsuperuser")

    @staticmethod
    def _asset(filename: str, name: str | None = None) -> ContentFile:
        path = ASSETS / filename
        content = ContentFile(path.read_bytes())
        content.name = name or filename
        return content
