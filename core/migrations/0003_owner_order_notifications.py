"""Owner order notifications, and stop charging for delivery.

Adds the address new-order emails are sent to, and zeroes the stored delivery
settings so nothing can reintroduce a fee at checkout. Only the settings
singleton is touched: historical ``orders.Order`` rows keep the delivery fee
and total they were created with.
"""

from decimal import Decimal

import django.core.validators
from django.db import migrations, models

ZERO = Decimal("0.00")


def stop_charging_for_delivery(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    SiteSettings.objects.update(default_delivery_fee=ZERO, free_delivery_threshold=None)


def noop(apps, schema_editor):
    """Nothing to restore: the old fee was a default, not customer data."""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_official_business_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="order_notification_email",
            field=models.EmailField(
                blank=True,
                help_text=(
                    "Every new order is emailed here, with the customer's details and a WhatsApp button. "
                    "Leave it empty to turn the notifications off; orders are still saved either way. "
                    "This address is never shown to customers."
                ),
                max_length=254,
                verbose_name="email address for new-order notifications",
            ),
        ),
        migrations.AlterField(
            model_name="sitesettings",
            name="default_delivery_fee",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Not used: delivery is agreed with each customer on WhatsApp after the order.",
                max_digits=8,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                verbose_name="default delivery fee",
            ),
        ),
        migrations.RunPython(stop_charging_for_delivery, noop),
    ]
