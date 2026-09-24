"""WCAG contrast helpers so brand colours never produce unreadable text."""

from __future__ import annotations

from core.validators import is_valid_hex_color

DARK_TEXT = "#251D21"
LIGHT_TEXT = "#FFFFFF"
FALLBACK_PRIMARY = "#F8C8DC"
FALLBACK_SECONDARY = "#9E526F"


def _channel(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(color_a: str, color_b: str) -> float:
    la, lb = relative_luminance(color_a), relative_luminance(color_b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def safe_hex(value: str | None, fallback: str = FALLBACK_PRIMARY) -> str:
    return value.upper() if is_valid_hex_color(value) else fallback


def readable_text_color(background: str | None) -> str:
    """Pick dark or white text, whichever has the higher contrast on ``background``."""
    background = safe_hex(background)
    if contrast_ratio(background, DARK_TEXT) >= contrast_ratio(background, LIGHT_TEXT):
        return DARK_TEXT
    return LIGHT_TEXT
