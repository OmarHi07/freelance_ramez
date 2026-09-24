"""Adopt the official business name ``rawnaq_accessories1``.

Updates the ``store_name_ar`` / ``store_name_en`` defaults and rewrites the
existing singleton row. No other data is touched.
"""

from django.db import migrations, models

from core.constants import BUSINESS_NAME


def set_official_name(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    SiteSettings.objects.update(store_name_ar=BUSINESS_NAME, store_name_en=BUSINESS_NAME)


def noop(apps, schema_editor):
    """The previous demo names are not restored: the official name is authoritative."""


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="sitesettings",
            name="store_name_ar",
            field=models.CharField(default=BUSINESS_NAME, max_length=120, verbose_name="store name (Arabic)"),
        ),
        migrations.AlterField(
            model_name="sitesettings",
            name="store_name_en",
            field=models.CharField(default=BUSINESS_NAME, max_length=120, verbose_name="store name (English)"),
        ),
        migrations.RunPython(set_official_name, noop),
    ]
