from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CartConfig(AppConfig):
    name = "cart"
    verbose_name = _("Cart")

    def ready(self):
        from cart import signals  # noqa: F401
