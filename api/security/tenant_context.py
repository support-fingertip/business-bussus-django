"""Tenant-schema context for code that runs OUTSIDE the request lifecycle.

Phase 1's ``schema_authority.pin_request_tenant`` and Phase 2's
``TenantSchemaMiddleware`` only fire for HTTP requests. Background work
(Celery tasks, Channels WebSocket consumers, management commands) does
NOT go through that path, so the connection's ``search_path`` stays at
``public`` — and any ORM query against a per-tenant model
(``Profile.objects.get(...)``, etc.) silently reads from the wrong
schema.

This module gives those callers a tight context manager / decorator
pair so the right tenant is pinned for the duration of the work and
restored afterwards. The contextvars set here flow through the
correlation-ID logging filter so all log lines emitted inside the
context are tagged with the tenant.

Usage from a Celery task::

    from celery import shared_task
    from api.security.tenant_context import tenant_schema_required

    @shared_task
    @tenant_schema_required("tenant_schema")
    def process_due_email_campaigns(tenant_schema, ...):
        # search_path is now `tenant_schema, public` for the body of
        # this task. ORM queries auto-scope. Reset on exit.
        Campaign.objects.filter(status="draft").update(...)

Usage from arbitrary code (Channels consumer, management command)::

    from api.security.tenant_context import with_tenant_schema

    with with_tenant_schema("tenant_alpha"):
        # ORM queries here scope to tenant_alpha
        ...

Always treat ``tenant_schema`` as untrusted — the helpers run it
through ``validate_identifier`` before any SQL.
"""

from __future__ import annotations

import contextlib
import functools
import logging
import threading
from typing import Callable, Iterator, Optional

from django.db import connection

from api.ORM.sqlFunctions.utils.helpers import validate_identifier
from api.security.correlation import set_tenant_id, set_user_id

logger = logging.getLogger(__name__)


# Re-entrancy: a task may invoke a helper that itself opens a
# tenant context. Track the current schema in a thread-local so nested
# `with_tenant_schema` calls restore the parent's schema, not `public`.
_state = threading.local()


def _stack() -> list[str]:
    if not hasattr(_state, "stack"):
        _state.stack = []
    return _state.stack


def get_current_schema() -> Optional[str]:
    """Return the innermost pinned schema, or None if no context is active."""
    s = _stack()
    return s[-1] if s else None


@contextlib.contextmanager
def with_tenant_schema(
    schema: str,
    *,
    user_id: Optional[str] = None,
) -> Iterator[None]:
    """Pin ``schema`` as the connection's search_path for the duration.

    Re-entrant: nested invocations push/pop on a thread-local stack.
    The outer invocation resets to ``public`` on exit; nested
    invocations restore the parent's schema.

    ``user_id`` is optional — if provided, it's also set on the
    correlation contextvar so log lines emitted inside the context
    carry it.
    """
    validate_identifier(schema, "schema")

    parent = get_current_schema()
    _stack().append(schema)
    set_tenant_id(schema)
    if user_id is not None:
        set_user_id(user_id)

    try:
        with connection.cursor() as cur:
            cur.execute("SET search_path TO %s, public", [schema])
        try:
            yield
        finally:
            with connection.cursor() as cur:
                if parent:
                    cur.execute("SET search_path TO %s, public", [parent])
                else:
                    cur.execute("SET search_path TO public")
    except Exception:
        # Even on error inside `yield`, make sure the stack stays
        # consistent. The cursor reset above handles SQL state; this
        # handles the in-process bookkeeping.
        raise
    finally:
        popped = _stack().pop()
        if popped != schema:
            logger.error(
                "tenant_context stack corrupted: popped %s, expected %s",
                popped, schema,
            )
        # Restore the contextvars to the parent's tenant.
        set_tenant_id(parent)
        if user_id is not None:
            set_user_id(None)


def tenant_schema_required(
    arg: Optional[str | Callable] = "tenant_schema",
) -> Callable:
    """Decorator: wrap a Celery task / function so it auto-pins the schema.

    The decorated callable must accept the schema either as the named
    keyword argument indicated by ``arg`` (default ``"tenant_schema"``)
    or as the first positional argument when ``bind=False``. The
    decorator pulls it out, calls ``with_tenant_schema``, and runs the
    body inside the context.

    For Celery tasks decorated with ``bind=True`` (so the first arg is
    ``self``), pass the schema as a kwarg or as the second positional.

    Usage:

        @shared_task
        @tenant_schema_required()
        def my_task(tenant_schema, *args, **kwargs):
            ...
    """

    # Allow bare ``@tenant_schema_required`` (no parens) usage.
    if callable(arg):
        return tenant_schema_required("tenant_schema")(arg)

    kwarg_name = arg

    def _wrap(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            schema = kwargs.get(kwarg_name)
            if schema is None and args:
                # Heuristic: if the first arg looks like a Celery task
                # `self` (has `.request` attribute), use args[1];
                # otherwise use args[0].
                first = args[0]
                if hasattr(first, "request") and hasattr(first, "name"):
                    if len(args) > 1:
                        schema = args[1]
                else:
                    schema = first
            if not schema:
                raise ValueError(
                    f"{fn.__name__} requires a tenant schema (kwarg "
                    f"{kwarg_name!r} or first positional argument). "
                    f"Background tasks MUST carry tenant context."
                )
            with with_tenant_schema(str(schema)):
                return fn(*args, **kwargs)

        return wrapper

    return _wrap


def with_user_tenant(user_id: str) -> contextlib.AbstractContextManager:
    """Open a tenant context for ``user_id`` by resolving their org.

    Use when a Celery task only knows the user but needs to run ORM
    queries against the user's tenant.
    """
    from api.security.schema_authority import resolve_tenant

    ctx = resolve_tenant(
        user_id=user_id,
        asserted_org_id=None,
        asserted_schema=None,
        asserted_profile_id=None,
    )
    return with_tenant_schema(ctx.schema, user_id=user_id)
