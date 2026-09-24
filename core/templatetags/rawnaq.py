"""Presentation helpers. Business rules live in service modules, not here."""

from __future__ import annotations

from django import template
from django.templatetags.static import static
from django.utils.html import format_html

from core import colors, constants
from core.formatting import format_money
from core.i18n import localized_value

register = template.Library()


@register.filter
def money(value) -> str:
    return format_money(value)


@register.filter
def localized(obj, field: str) -> str:
    if obj is None:
        return ""
    return localized_value(obj, field)


@register.filter
def safe_hex(value, fallback: str = colors.FALLBACK_PRIMARY) -> str:
    return colors.safe_hex(value, fallback)


@register.filter
def text_on(value) -> str:
    """Readable text colour (dark or white) for a background colour."""
    return colors.readable_text_color(value)


@register.simple_tag
def business_name() -> str:
    """The official business name, never translated or reformatted."""
    return constants.BUSINESS_NAME


@register.simple_tag
def icon(name: str, css_class: str = "icon") -> str:
    """Inline reference to the local SVG sprite (decorative, hidden from screen readers)."""
    sprite = static("img/icons.svg")
    return format_html(
        '<svg class="{}" aria-hidden="true" focusable="false"><use href="{}#{}"></use></svg>',
        css_class,
        sprite,
        name,
    )


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def startswith(value, prefix: str) -> bool:
    return str(value or "").startswith(prefix)
