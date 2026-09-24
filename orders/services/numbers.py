"""Readable, non-sequential order numbers such as ``RNQ-20260921-AB12``."""

from __future__ import annotations

import secrets

from django.utils import timezone

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I to avoid confusion
PREFIX = "RNQ"
SUFFIX_LENGTH = 4


def generate_order_number(now=None) -> str:
    local_now = timezone.localtime(now or timezone.now())
    suffix = "".join(secrets.choice(ALPHABET) for _ in range(SUFFIX_LENGTH))
    return f"{PREFIX}-{local_now:%Y%m%d}-{suffix}"


def unique_order_number(exists, now=None, attempts: int = 20) -> str:
    """Generate a number for which ``exists(number)`` is False."""
    for _ in range(attempts):
        number = generate_order_number(now)
        if not exists(number):
            return number
    raise RuntimeError("Could not generate a unique order number.")
