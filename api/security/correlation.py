"""Correlation-ID middleware and contextual log filter.

Every incoming request is tagged with a stable trace_id (from incoming
``X-Request-ID`` header if the load balancer set one, else a fresh
UUID4) plus the resolved tenant_id and user_id once the dispatcher has
reconciled them.

These three values are stitched into every log line via the
``RequestContextFilter`` filter so:
  - operations can grep logs by trace_id and follow a request across
    APIs / BL / ORM / Celery boundaries,
  - support can search "show me everything user X did between 09:00 and
    09:05" without expensive joins,
  - tenant-isolation regressions are visible in the log stream itself.

The middleware uses ``contextvars`` so log lines emitted from background
threads (Channels consumers, ThreadPoolExecutor workers) inherit the
parent request's IDs automatically.
"""

from __future__ import annotations

import contextvars
import logging
import uuid
from typing import Optional

from django.utils.deprecation import MiddlewareMixin


_TRACE_ID: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "trace_id", default=None
)
_TENANT_ID: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "tenant_id", default=None
)
_USER_ID: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "user_id", default=None
)


REQUEST_ID_HEADER = "HTTP_X_REQUEST_ID"
RESPONSE_HEADER = "X-Request-ID"


def get_trace_id() -> Optional[str]:
    return _TRACE_ID.get()


def get_tenant_id() -> Optional[str]:
    return _TENANT_ID.get()


def get_user_id() -> Optional[str]:
    return _USER_ID.get()


def set_tenant_id(tenant_id: Optional[str]) -> None:
    """Called from ``schema_authority.pin_request_tenant`` once the
    reconciliation has succeeded so subsequent log lines on the same
    request carry the canonical tenant id."""
    _TENANT_ID.set(tenant_id)


def set_user_id(user_id: Optional[str]) -> None:
    _USER_ID.set(user_id)


class RequestCorrelationMiddleware(MiddlewareMixin):
    """Tag every request with a trace_id and propagate it on the way out."""

    def process_request(self, request):
        incoming = request.META.get(REQUEST_ID_HEADER)
        trace_id = incoming or uuid.uuid4().hex
        _TRACE_ID.set(trace_id)
        # Reset tenant/user — they'll be filled in by schema_authority and
        # the auth layer respectively when those have run.
        _TENANT_ID.set(None)
        _USER_ID.set(None)
        request.trace_id = trace_id

    def process_response(self, request, response):
        try:
            response[RESPONSE_HEADER] = (
                getattr(request, "trace_id", None) or _TRACE_ID.get() or ""
            )
        except Exception:
            # Defensive: never let header-write errors break the response.
            pass
        return response


class RequestContextFilter(logging.Filter):
    """Inject the contextvars triple into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_trace_id() or "-"
        record.tenant_id = get_tenant_id() or "-"
        record.user_id = get_user_id() or "-"
        return True
