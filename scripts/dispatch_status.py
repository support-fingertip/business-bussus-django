"""Dual-path dispatch flag inspector.

Operator tool for the Phase 2.B + 3.C + 4.B soak. Reads the three
feature-flag env vars, prints their state, and lists how many
dispatch sites each one controls. Run on every staging / canary
instance to verify the flag state matches what you intended.

Output is plain text (terminal-friendly) — no JSON, no formatting
deps. Designed to be greppable in deploy logs.

Usage:
    python scripts/dispatch_status.py

Exit codes:
    0  — at least one flag is set; output reflects the current state
    0  — all flags off (still informational, not an error)
    2  — could not read the env (shouldn't normally happen)

This script is read-only. It does NOT modify env, does NOT touch
the database, and does NOT require Django to be configured.
"""

from __future__ import annotations

import os
import sys


# Mirror of api.permissions._orm_dispatch.is_orm_enabled — kept in sync by
# the test in tests/permissions/test_dispatch_status.py.
_TRUTHY = {"1", "true", "yes", "on"}


def _is_on(flag: str) -> bool:
    return os.getenv(flag, "0").strip().lower() in _TRUTHY


# Flag → (number of sites controlled, brief description). Update this
# table when new flags are added or sites are deleted.
#
# Counts come from the Phase X operator notes; the cumulative table at
# the bottom of docs/SOAK_RUNBOOK.md is the source of truth.
FLAGS: list[tuple[str, int, str]] = [
    (
        "USE_ORM_FOR_PERMISSIONS",
        5,
        "permissions.py setup-table CRUD via Django ORM",
    ),
    (
        "USE_ORM_FOR_BL",
        17,
        "BL files using Wave 3-5 + Phase 3.B tenant models",
    ),
    (
        "USE_DYNAMIC_GATEWAY",
        4,
        "Dynamic-object CRUD (D/U/I/S) via the gateway",
    ),
]


def _format_state(on: bool) -> str:
    return "ON  " if on else "off "


def _next_action(states: list[bool]) -> int | None:
    """Return the index of the next flag to enable per the recommended
    rollout order, or None if all are on."""
    for i, on in enumerate(states):
        if not on:
            return i
    return None


def main() -> int:
    print("=" * 60)
    print("Dual-path dispatch flag status")
    print("=" * 60)

    states: list[bool] = []
    name_width = max(len(f) for f, _, _ in FLAGS)

    for flag, n_sites, _ in FLAGS:
        on = _is_on(flag)
        states.append(on)
        sites_label = f"{n_sites} site{'s' if n_sites != 1 else ''} controlled"
        print(f"{flag:<{name_width}}  =  {_format_state(on)} ({sites_label})")

    soak_log_level = os.getenv("SOAK_LOG_LEVEL", "DEBUG")
    print()
    print(f"{'SOAK_LOG_LEVEL':<{name_width}}  =  {soak_log_level}")
    print()

    print("Recommended rollout order:")
    next_idx = _next_action(states)
    for i, (flag, _, _) in enumerate(FLAGS):
        on = states[i]
        if on:
            marker = "✓ on"
        elif i == next_idx:
            marker = "→ next"
        else:
            marker = "  later"
        print(f"  {i + 1}. {flag:<{name_width}}  {marker}")

    if next_idx is None:
        print()
        print("All flags ON. After Stage 4 soak completes, proceed to Stage 5")
        print("(delete raw paths) per docs/SOAK_RUNBOOK.md.")
    elif any(states):
        print()
        print(f"Continue with stage 2/3/4 of FLAGS[{next_idx}] = "
              f"{FLAGS[next_idx][0]} per docs/SOAK_RUNBOOK.md once the")
        print("currently-on flag has cleared its exit criteria.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
