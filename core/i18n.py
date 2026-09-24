"""Helpers for bilingual database content stored in explicit ``_ar``/``_en`` fields."""

from __future__ import annotations

from django.conf import settings
from django.utils.translation import get_language


def active_language_code() -> str:
    language = (get_language() or settings.LANGUAGE_CODE).lower()
    return "en" if language.startswith("en") else "ar"


def localized_value(obj, field: str) -> str:
    """Return ``obj.<field>_<lang>`` for the active language, falling back to the other one."""
    primary = active_language_code()
    secondary = "ar" if primary == "en" else "en"
    value = getattr(obj, f"{field}_{primary}", "") or ""
    if not value:
        value = getattr(obj, f"{field}_{secondary}", "") or ""
    return value


class LocalizedFieldsMixin:
    """Adds ``obj.localized('name')`` to models with ``name_ar``/``name_en`` fields."""

    def localized(self, field: str) -> str:
        return localized_value(self, field)
