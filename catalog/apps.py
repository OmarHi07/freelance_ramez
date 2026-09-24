from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CatalogConfig(AppConfig):
    name = "catalog"
    verbose_name = _("Catalogue")

    def ready(self):
        from catalog import signals  # noqa: F401
