"""Business constants confirmed by the store owner.

``BUSINESS_NAME`` is the single canonical spelling of the official business
name. It is never translated, capitalised or reformatted: Arabic and English
pages both render it exactly as written here (inside ``dir="ltr"`` on Arabic
pages). Templates read it through the ``{% business_name %}`` tag and Python
code imports it from this module, so the literal exists in one place only.

The remaining values are only *defaults*: the live values are editable in
SiteSettings from the owner dashboard.
"""

from decimal import Decimal

BUSINESS_NAME = "rawnaq_accessories1"
# The official name is identical in both languages; the store-name defaults and
# the SiteSettings singleton both point at it.
STORE_NAME_EN = BUSINESS_NAME
STORE_NAME_AR = BUSINESS_NAME
INSTAGRAM_HANDLE = BUSINESS_NAME
INSTAGRAM_URL = f"https://www.instagram.com/{BUSINESS_NAME}/"
WHATSAPP_DISPLAY_NUMBER = "0553003327"
WHATSAPP_INTERNATIONAL_NUMBER = "972553003327"
CURRENCY_SYMBOL = "₪"
# Delivery is quoted per order on WhatsApp, so checkout never adds a fee.
DEFAULT_DELIVERY_FEE = Decimal("0.00")
MONEY_QUANTUM = Decimal("0.01")
