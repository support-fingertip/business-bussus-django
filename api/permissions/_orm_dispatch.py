"""Phase 2.B + 3.C — feature-flagged dispatch from raw SQL to ORM.

Each public function in the codebase that previously executed raw SQL
against a tenant-modeled table can now have two implementations:
``_<name>_raw()`` (the legacy, byte-identical path) and
``_<name>_orm()`` (the new path against the Phase 2/3 tenant models).
The wrapper picks one based on the env var named in the dispatch
call.

Each functional area gets its own flag so they can roll out
independently:

  USE_ORM_FOR_PERMISSIONS  — Phase 2.B (permissions.py)
  USE_ORM_FOR_BL           — Phase 3.C (BL files using Wave 3-5 models)
  USE_DYNAMIC_GATEWAY      — Phase 4.B (dynamic-object CRUD via the
                             api.ORM.dynamic gateway; first wave: DELETE)

Default for every flag is OFF — operators flip it after they've
soaked enough traffic on the new path. Per-call DEBUG logging records
which path was taken so dashboards can show coverage during rollout.

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


# Default env var name (Phase 2.B). Phase 3.C BL callers pass their
# own env var via the `flag` parameter on `dispatch`.
DEFAULT_FLAG = "USE_ORM_FOR_PERMISSIONS"


def is_orm_enabled(flag: str = DEFAULT_FLAG) -> bool:
    """Return True iff the given flag env var is truthy."""
    return os.getenv(flag, "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def dispatch(
    name: str,
    raw_impl: Callable[[], T],
    orm_impl: Callable[[], T],
    *,
    flag: str = DEFAULT_FLAG,
) -> T:
    """Pick the active implementation and invoke it.

    ``name`` is used purely for the per-call DEBUG log so dashboards
    can show how often each path runs during the soak window.
    ``flag`` defaults to ``USE_ORM_FOR_PERMISSIONS`` for Phase 2.B
    backward compatibility; Phase 3.C BL callers pass
    ``flag="USE_ORM_FOR_BL"``.
    """
    if is_orm_enabled(flag):
        logger.debug("%s.%s: ORM path", flag, name)
        return orm_impl()
    logger.debug("%s.%s: raw-SQL path", flag, name)
    return raw_impl()
