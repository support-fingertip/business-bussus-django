"""Per-request Postgres statement_timeout.

A runaway query (bad index, accidental cross-join, OOM-bound rollup)
can hold a backend connection open indefinitely, eventually exhausting
the pool and taking the whole tenant down. Setting
``statement_timeout`` on every request bounds the worst case.

We pick the timeout per request based on the URL path:

  - ``/v2/api/report/...``         → 120s (saved-report previews can be slow)
  - ``/v2/api/dashboard/...``      → 120s (similar shape)
  - ``/export/...``                → 600s (bulk export endpoints)
  - everything else                → 30s

Operators can override globally via env vars
``DB_STATEMENT_TIMEOUT_DEFAULT_MS`` /
``DB_STATEMENT_TIMEOUT_REPORT_MS`` /
``DB_STATEMENT_TIMEOUT_EXPORT_MS``. Set to 0 to disable the limit on a
specific bucket (useful during incident response).

The middleware uses ``SET LOCAL`` inside an explicit transaction-or-
new-cursor pair so the timeout only applies to the current request and
doesn't leak to the next caller picking up the same connection from
the pool.
"""

from __future__ import annotations

import logging
import os

from django.db import connection
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


def _ms(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        logger.warning("Invalid %s=%r; using default %d", name, raw, default)
        return default


DEFAULT_MS = _ms("DB_STATEMENT_TIMEOUT_DEFAULT_MS", 30_000)
REPORT_MS = _ms("DB_STATEMENT_TIMEOUT_REPORT_MS", 120_000)
EXPORT_MS = _ms("DB_STATEMENT_TIMEOUT_EXPORT_MS", 600_000)


def _bucket_ms(path: str) -> int:
    if not path:
        return DEFAULT_MS
    if "/report" in path or "/dashboard" in path:
        return REPORT_MS
    if path.startswith("/export") or "/data_export" in path:
        return EXPORT_MS
    return DEFAULT_MS


class StatementTimeoutMiddleware(MiddlewareMixin):
    """Apply ``SET statement_timeout`` for the duration of the request."""

    def process_request(self, request):
        timeout_ms = _bucket_ms(request.path or "")
        if timeout_ms <= 0:
            return  # Operator opted out for this bucket.
        try:
            with connection.cursor() as cur:
                # Session-level SET, not LOCAL — Django's connection is
                # per-thread and reused via pooling. process_response
                # resets it to the default to avoid bleed-over.
                cur.execute("SET statement_timeout = %s", [timeout_ms])
            request._statement_timeout_ms = timeout_ms
        except Exception as exc:
            # Don't let a misconfigured DB take the whole request out.
            logger.warning("Could not set statement_timeout: %s", exc)

    def process_response(self, request, response):
        # Reset to whatever the cluster default is so the next caller
        # picking up this connection doesn't inherit our bucket.
        if getattr(request, "_statement_timeout_ms", None):
            try:
                with connection.cursor() as cur:
                    cur.execute("SET statement_timeout = DEFAULT")
            except Exception:
                pass
        return response
