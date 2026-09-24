"""Money formatting shared by templates and message builders."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from core.constants import CURRENCY_SYMBOL, MONEY_QUANTUM


def quantize_money(value) -> Decimal:
    return Decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def format_money(value) -> str:
    """Format a Decimal as ``₪1,234.50``."""
    if value is None or value == "":
        return ""
    amount = quantize_money(value)
    return f"{CURRENCY_SYMBOL}{amount:,.2f}"
