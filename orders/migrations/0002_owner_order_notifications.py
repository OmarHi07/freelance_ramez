"""Track the owner notification email per order.

Adds nullable timestamps only, so no existing order changes. The customer
no longer opens WhatsApp themselves, so ``whatsapp_opened_at`` becomes a
read-only legacy field: it is kept rather than dropped so historical rows
do not lose the data they recorded.
"""


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='owner_notification_attempted_at',
            field=models.DateTimeField(blank=True, editable=False, null=True, verbose_name='owner notified: last attempt'),
        ),
        migrations.AddField(
            model_name='order',
            name='owner_notification_sent_at',
            field=models.DateTimeField(blank=True, editable=False, null=True, verbose_name='owner notified: sent'),
        ),
        migrations.AlterField(
            model_name='order',
            name='whatsapp_opened_at',
            field=models.DateTimeField(blank=True, editable=False, null=True, verbose_name='WhatsApp opened at (legacy)'),
        ),
    ]
