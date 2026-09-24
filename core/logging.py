"""Structured JSON log formatter for production.

Only technical metadata is emitted. Request objects, POST bodies and other
customer personal data are never serialised.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

_SAFE_EXTRA_KEYS = ("status_code", "order_id", "order_number", "event", "duration_ms")


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in _SAFE_EXTRA_KEYS:
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        request = getattr(record, "request", None)
        if request is not None:
            payload["method"] = getattr(request, "method", None)
            payload["path"] = getattr(request, "path", None)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)
