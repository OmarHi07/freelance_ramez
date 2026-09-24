"""Privacy housekeeping: remove shared coordinates from finished orders.

    python manage.py purge_order_locations --days 30

Clears latitude, longitude, accuracy and the consent timestamp from orders that
were delivered or cancelled more than ``--days`` days ago. The written address
snapshot is kept for the order record.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from orders.models import Order, OrderStatus


class Command(BaseCommand):
    help = "Remove stored GPS coordinates from delivered/cancelled orders older than N days."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=options["days"])
        queryset = Order.objects.filter(
            status__in=[OrderStatus.DELIVERED, OrderStatus.CANCELLED],
            updated_at__lt=cutoff,
            latitude__isnull=False,
        )
        count = queryset.count()
        if not options["dry_run"]:
            queryset.update(latitude=None, longitude=None, location_accuracy_m=None, location_consent_at=None)
        verb = "Would clear" if options["dry_run"] else "Cleared"
        self.stdout.write(self.style.SUCCESS(f"{verb} coordinates on {count} finished orders."))
