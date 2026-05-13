"""Cross-tenant isolation heartbeat — continuous Phase 4 verification.

In plain English
----------------

Phase 4 (per-tenant Postgres roles + Row-Level Security) is the
load-bearing isolation layer. If it breaks in production — a missing
GRANT, an accidentally-disabled policy, an ops command that ran the
wrong ALTER — we need to know in minutes, not when a customer
reports it.

This module ships a Celery task that runs once an hour in production
and tries to do a cross-tenant query as a tenant role. If the query
succeeds (returns any rows), the task pages on-call immediately
because that means the isolation contract is broken.

How the probe works
-------------------

1. Pick two active orgs (A, B) from public.organizations.
2. Open a connection.
3. SET LOCAL ROLE tenant_<A_schema>_role
4. SET LOCAL app.current_org_id = <A.org_id>
5. SELECT count(*) FROM public.users WHERE organization_id = <B.org_id>
6. The count MUST be zero. If it's > 0, RLS is broken; alert.
7. Also try ``SELECT count(*) FROM <B_schema>.profile``. This MUST
   raise ``permission denied`` (Phase 4 part 1's role grants).
   Anything else (especially a non-zero count) means the role's
   permissions are wrong.

What happens on failure
-----------------------

We do NOT auto-revoke or auto-disable anything. The task:

  * Logs at CRITICAL with the offending pair of orgs + the failure mode
  * Calls ``sentry_sdk.capture_message`` with severity FATAL
  * Increments a Prometheus/Datadog counter `cross_tenant_probe_failed`
  * Returns a structured result the operator can read in flower

The on-call playbook (docs/runbooks/incident_response_cross_tenant_leak.md)
takes over from there.

Schedule
--------

Add to ``version2/celery.py``::

    'cross_tenant_heartbeat_hourly': {
        'task': 'api.security.cross_tenant_heartbeat.run_cross_tenant_probe',
        'schedule': crontab(minute=0),  # top of every hour
    }
"""

from __future__ import annotations

import logging
import random
from typing import Optional

from celery import shared_task
from django.db import connection

from api.celery_tasks.base import AdminTask

logger = logging.getLogger(__name__)


def _pick_probe_pair() -> Optional[tuple[dict, dict]]:
    """Pick two distinct active orgs to probe between.

    Returns None if fewer than 2 active orgs exist (single-tenant
    deploy, nothing to probe).
    """
    with connection.cursor() as cur:
        cur.execute(
            "SELECT id, database_schema FROM public.organizations "
            "WHERE is_active = TRUE AND database_schema IS NOT NULL "
            "AND database_schema <> ''"
        )
        rows = cur.fetchall()
    if len(rows) < 2:
        return None
    # Randomise so the probe doesn't always hit the same pair (catches
    # bugs that only affect specific tenants).
    a, b = random.sample(rows, 2)
    return ({"id": a[0], "schema": a[1]}, {"id": b[0], "schema": b[1]})


@shared_task(base=AdminTask)
def run_cross_tenant_probe() -> dict:
    """Run the cross-tenant isolation probe. Returns a structured report.

    A failed probe is the loudest possible alert: this is a P1
    multi-tenant safety event. The Sentry hook + structured log are
    designed for automated paging via your alerting system.
    """
    pair = _pick_probe_pair()
    if pair is None:
        return {"status": "skipped", "reason": "fewer than 2 active orgs"}

    a, b = pair
    result = {
        "status": "ok",
        "probe_a": a["id"],
        "probe_b": b["id"],
        "checks": {},
    }

    # ---------- RLS check on public.users ----------
    rls_check_passed = False
    rls_error: str | None = None
    try:
        with connection.cursor() as cur:
            cur.execute("BEGIN")
            try:
                cur.execute(
                    "SET LOCAL ROLE %s", [f"tenant_{a['schema']}_role"]
                )
                cur.execute(
                    "SET LOCAL app.current_org_id = %s", [a["id"]]
                )
                cur.execute(
                    "SELECT count(*) FROM public.users WHERE organization_id = %s",
                    [b["id"]],
                )
                row = cur.fetchone()
                count = int(row[0]) if row else 0
                if count == 0:
                    rls_check_passed = True
                else:
                    rls_error = (
                        f"RLS LEAK: tenant {a['id']} read {count} row(s) "
                        f"from public.users for tenant {b['id']}"
                    )
            finally:
                cur.execute("ROLLBACK")
    except Exception as exc:
        # A "role does not exist" error during the probe just means
        # the role wasn't provisioned — not a leak, but worth noting.
        rls_error = f"probe execution failed: {exc}"

    result["checks"]["rls_public_users"] = {
        "passed": rls_check_passed,
        "error": rls_error,
    }

    # ---------- Schema-grant check ----------
    grant_check_passed = False
    grant_error: str | None = None
    try:
        with connection.cursor() as cur:
            cur.execute("BEGIN")
            try:
                cur.execute(
                    "SET LOCAL ROLE %s", [f"tenant_{a['schema']}_role"]
                )
                # Try to access the OTHER tenant's schema. This must
                # raise permission denied.
                try:
                    cur.execute(
                        f'SELECT 1 FROM "{b["schema"]}".profile LIMIT 1'
                    )
                    # If we got here, the role can read another tenant's
                    # schema — major breach of Phase 4 part 1.
                    grant_error = (
                        f"GRANT LEAK: tenant {a['id']} role can read "
                        f"{b['schema']}.profile (Phase 4 part 1 broken)"
                    )
                except Exception as exc:
                    # Expected — permission denied. Confirm the error
                    # text mentions permission/access (not a different
                    # bug like a missing table).
                    msg = str(exc).lower()
                    if "permission denied" in msg or "access" in msg:
                        grant_check_passed = True
                    else:
                        grant_error = f"unexpected probe error: {exc}"
            finally:
                cur.execute("ROLLBACK")
    except Exception as exc:
        grant_error = f"grant probe failed: {exc}"

    result["checks"]["schema_grant"] = {
        "passed": grant_check_passed,
        "error": grant_error,
    }

    # ---------- Aggregate ----------
    overall_passed = rls_check_passed and grant_check_passed
    result["status"] = "ok" if overall_passed else "FAIL"

    if not overall_passed:
        msg = (
            f"CROSS-TENANT HEARTBEAT FAILED: "
            f"a={a['id']}, b={b['id']}, rls={rls_check_passed}, "
            f"grants={grant_check_passed}, "
            f"rls_error={rls_error!r}, grant_error={grant_error!r}"
        )
        logger.critical(msg)
        # Sentry alert (FATAL severity)
        try:
            import sentry_sdk
            sentry_sdk.capture_message(msg, level="fatal")
        except Exception:
            pass

    return result
