from django.utils.translation import get_language_bidi

from core.i18n import active_language_code
from core.models import get_site_settings


def storefront(request):
    """Values used by the base layout on every page."""
    from cart.services import cart_item_count

    def _cart_count():
        return cart_item_count(request)

    return {
        "site_settings": get_site_settings(request),
        "cart_count": _cart_count,
        "lang_code": active_language_code(),
        "is_rtl": get_language_bidi(),
    }
