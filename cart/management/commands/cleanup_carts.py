from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from cart.models import Cart


class Command(BaseCommand):
    help = "Delete anonymous carts that have not been updated for a while (default 30 days)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=settings.ANONYMOUS_CART_MAX_AGE_DAYS)

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=options["days"])
        deleted, _details = Cart.objects.filter(user__isnull=True, updated_at__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} stale anonymous cart rows."))
