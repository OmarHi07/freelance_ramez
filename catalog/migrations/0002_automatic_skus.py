"""SKUs become generated, non-editable codes.

Both defaults are Python-level callables, so this migration only changes
field metadata: every SKU already stored keeps its exact value, including
codes that were assigned by hand. Order-item SKU snapshots live on
``orders.OrderItem`` and are not touched at all.
"""


import catalog.skus
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='product',
            name='sku',
            field=models.CharField(default=catalog.skus.generate_product_sku, editable=False, help_text='Generated automatically. It never changes once the product exists.', max_length=64, unique=True, verbose_name='product code (SKU)'),
        ),
        migrations.AlterField(
            model_name='productvariant',
            name='sku',
            field=models.CharField(default=catalog.skus.generate_variant_sku, editable=False, help_text='Generated automatically. It never changes once the option exists.', max_length=64, unique=True, verbose_name='option code (SKU)'),
        ),
    ]
