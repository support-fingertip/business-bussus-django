"""Phase 2.B + 3.C + 4.B — feature-flagged dispatch from raw SQL to ORM.

Each public function in the codebase that previously executed raw SQL
against a tenant-modeled table can now have two implementations:
``_<name>_raw()`` (the legacy, byte-identical path) and
``_<name>_orm()`` (the new path against the Phase 2/3 tenant models or
the api.ORM.dynamic gateway). The wrapper picks one based on the env
var named in the dispatch call.

Each functional area gets its own flag so they can roll out
independently:

  USE_ORM_FOR_PERMISSIONS  — Phase 2.B (permissions.py)
  USE_ORM_FOR_BL           — Phase 3.C (BL files using Wave 3-5 + Phase 3.B models)
  USE_DYNAMIC_GATEWAY      — Phase 4.B (dynamic-object CRUD via the
                             api.ORM.dynamic gateway; waves 1-4 cover D/U/I/S)

Default for every flag is OFF — operators flip them after they've
soaked enough traffic on the new path. Per-call logging records which
path was taken so dashboards can show coverage during rollout.

By default the per-call log lines are at DEBUG level. During an active
soak the operator can promote them to INFO via ``SOAK_LOG_LEVEL=INFO``
without flipping the application's overall log level. The runbook at
``docs/SOAK_RUNBOOK.md`` makes this part of the standard staging
procedure.

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
# own env var via the `flag` parameter on `dispatch`. Phase 4.B
# callers use ``USE_DYNAMIC_GATEWAY``.
DEFAULT_FLAG = "USE_ORM_FOR_PERMISSIONS"


_TRUTHY = ("1", "true", "yes", "on")
_VALID_LEVEL_NAMES = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def is_orm_enabled(flag: str = DEFAULT_FLAG) -> bool:
    """Return True iff the given flag env var is truthy."""
    return os.getenv(flag, "0").strip().lower() in _TRUTHY


def _soak_log_level() -> int:
    """Resolve ``SOAK_LOG_LEVEL`` to a stdlib logging level int.

    Default is ``DEBUG``. Operators set ``SOAK_LOG_LEVEL=INFO`` during
    the active soak so dispatch lines hit production log streams
    without flipping the application's overall log level. Invalid
    values silently fall back to DEBUG — the dispatch helper isn't
    where we want to fail loudly on a misconfigured env var.
    """
    raw = os.getenv("SOAK_LOG_LEVEL", "DEBUG").strip().upper()
    if raw not in _VALID_LEVEL_NAMES:
        return logging.DEBUG
    return getattr(logging, raw)


def dispatch(
    name: str,
    raw_impl: Callable[[], T],
    orm_impl: Callable[[], T],
    *,
    flag: str = DEFAULT_FLAG,
) -> T:
    """Pick the active implementation and invoke it.

    ``name`` is used purely for the per-call log so dashboards can
    show how often each path runs during the soak window. ``flag``
    defaults to ``USE_ORM_FOR_PERMISSIONS`` for Phase 2.B backward
    compatibility; Phase 3.C BL callers pass ``flag="USE_ORM_FOR_BL"``;
    Phase 4.B callers pass ``flag="USE_DYNAMIC_GATEWAY"``.

    The log line goes out at the level resolved from ``SOAK_LOG_LEVEL``
    — DEBUG by default, INFO during a soak.
    """
    level = _soak_log_level()
    if is_orm_enabled(flag):
        logger.log(level, "%s.%s: ORM path", flag, name)
        return orm_impl()
    logger.log(level, "%s.%s: raw-SQL path", flag, name)
    return raw_impl()
