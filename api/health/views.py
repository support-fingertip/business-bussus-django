"""Health-check endpoints for k8s/ECS/load-balancer probes.

Three endpoints with intentionally different semantics:

  - ``/healthz``  — liveness. Returns 200 as long as the process is up
                    and able to render a response. No external deps.
                    Failures here mean the container should be killed.

  - ``/readyz``   — readiness. Returns 200 only when the process can
                    actually serve traffic: database reachable, cache
                    reachable, no startup tasks pending. Failures here
                    pull the container out of the LB rotation.

  - ``/livez``    — alias for ``/healthz``. Some orchestrators look here.

Endpoints are intentionally unauthenticated; they must respond before
authentication middleware would have a chance to run.
"""

from __future__ import annotations

import logging
import time

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@csrf_exempt
@require_GET
def liveness(request):
    """Always-up unless the process is hosed."""
    return JsonResponse({"status": "ok"}, status=200)


@csrf_exempt
@require_GET
def readiness(request):
    """Verify external dependencies are reachable.

    Returns 200 with per-component status when everything is good, 503
    with details otherwise. The response shape is stable so dashboards
    can scrape it.
    """
    components = {}
    overall_ok = True

    # ---- Postgres ----
    db_started = time.perf_counter()
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        components["database"] = {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - db_started) * 1000, 2),
        }
    except Exception as exc:
        overall_ok = False
        components["database"] = {"status": "error", "error": str(exc)[:200]}
        logger.warning("readiness: database unreachable: %s", exc)

    # ---- Cache (Redis) ----
    cache_started = time.perf_counter()
    try:
        probe_key = "_readyz_probe"
        cache.set(probe_key, "1", timeout=5)
        if cache.get(probe_key) != "1":
            raise RuntimeError("Cache write/read mismatch")
        components["cache"] = {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - cache_started) * 1000, 2),
        }
    except Exception as exc:
        overall_ok = False
        components["cache"] = {"status": "error", "error": str(exc)[:200]}
        logger.warning("readiness: cache unreachable: %s", exc)

    payload = {
        "status": "ok" if overall_ok else "error",
        "components": components,
    }
    return JsonResponse(payload, status=200 if overall_ok else 503)
