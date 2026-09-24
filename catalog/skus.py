"""Automatic SKU generation.

SKUs are internal stock codes, never owner input. They are generated once when
a row is created and then never change, so they stay stable while names,
brands, slugs and options are edited.

The random part is UUID4 hex, so codes can be generated concurrently without
coordination (``MAX(id) + 1`` is unsafe under parallel requests) and never
leak product names, Arabic text or brand names.
"""

from __future__ import annotations

import uuid

PRODUCT_SKU_PREFIX = "RAW-P-"
VARIANT_SKU_PREFIX = "RAW-V-"
SKU_RANDOM_LENGTH = 12  # hex characters -> 48 bits of entropy


def _random_code() -> str:
    return uuid.uuid4().hex[:SKU_RANDOM_LENGTH].upper()


def generate_product_sku() -> str:
    """Return a fresh product SKU, e.g. ``RAW-P-A1B2C3D4E5F6``."""
    return f"{PRODUCT_SKU_PREFIX}{_random_code()}"


def generate_variant_sku() -> str:
    """Return a fresh variant SKU, e.g. ``RAW-V-A1B2C3D4E5F6``."""
    return f"{VARIANT_SKU_PREFIX}{_random_code()}"
