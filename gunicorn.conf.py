"""Gunicorn configuration (production). Values can be tuned with environment variables."""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"  # noqa: S104 - container must listen on all interfaces
workers = int(os.environ.get("WEB_CONCURRENCY", "3"))
threads = int(os.environ.get("GUNICORN_THREADS", "2"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "30"))
graceful_timeout = 20
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
accesslog = "-"
errorlog = "-"
# Structured access log without client IPs or query strings (search terms may contain personal data).
access_log_format = (
    '{"logger": "gunicorn.access", "method": "%(m)s", "path": "%(U)s", "status": %(s)s, "duration_ms": %(M)s}'
)
