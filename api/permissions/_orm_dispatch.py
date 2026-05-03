"""Phase 2.B — feature-flagged dispatch from raw SQL to ORM.

Each public permission function in ``api/permissions/permissions.py``
that previously executed raw SQL now has two implementations:
``_<name>_raw()`` (the legacy, byte-identical path) and
``_<name>_orm()`` (the new path against the Phase 2 Wave 2 tenant
models). The wrapper picks one based on the ``USE_ORM_FOR_PERMISSIONS``
env var.

Default is OFF — operators flip it to ``1`` after they've soaked
enough traffic on the new path. Per-call logging (debug-level)
records which path was taken so dashboards can show coverage during
rollout.

The dispatch helper does NOT mask exceptions. If the ORM path raises,
it propagates — by design. We want bugs in the new code path to be
loud, not silently fall back to raw SQL (which would mask drift
between the two paths).
"""

from __future__ import annotations

import logging
import os
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)


T = TypeVar("T")


def is_orm_enabled() -> bool:
    """Return True iff USE_ORM_FOR_PERMISSIONS is truthy."""
    return os.getenv("USE_ORM_FOR_PERMISSIONS", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def dispatch(
    name: str,
    raw_impl: Callable[[], T],
    orm_impl: Callable[[], T],
) -> T:
    """Pick the active implementation and invoke it.

    ``name`` is used purely for the per-call DEBUG log so dashboards
    can show how often each path runs during the soak window.
    """
    if is_orm_enabled():
        logger.debug("permissions.%s: ORM path", name)
        return orm_impl()
    logger.debug("permissions.%s: raw-SQL path", name)
    return raw_impl()
