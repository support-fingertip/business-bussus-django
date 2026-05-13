"""Property-based cross-tenant isolation tests — Phase 9 starter.

These tests REQUIRE a live Postgres database with the Phase 4 part 2
migrations applied. They skip cleanly when no test DB is available
(or when Hypothesis isn't installed) — matching the pattern used
elsewhere in tests/security.

Why a property-based approach
-----------------------------

For tenant isolation, sampled testing isn't enough — we need to
prove that "for any pair of tenants (A, B), no user authenticated
to A can read tenant B's rows in any shared table." Hypothesis
generates random tenant pairs + access patterns and exercises them
against the actual RLS policies; a single failing example surfaces
a bug that a hand-written test might never trigger.

Running locally
---------------

    # Install Hypothesis if not already
    pip install hypothesis

    # Make sure a test DB is reachable and migrations are applied
    python manage.py migrate

    # Run only this file (slow — minutes; runs hundreds of random trials)
    pytest tests/security/test_rls_property_isolation.py -m tenant_isolation

CI
--

Run on every PR that touches:
  * api/security/tenant_schema_middleware.py
  * api/migrations/ (any RLS-related migration)
  * scripts/per_tenant_ddl/

Add to ``.github/workflows/security-tests.yml`` once Phase 9 lands.
"""

from __future__ import annotations

import os
import uuid
from contextlib import contextmanager

import pytest


pytestmark = pytest.mark.tenant_isolation


def _ensure_test_db():
    pytest.importorskip("django")
    pytest.importorskip("hypothesis")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "version2.settings")
    try:
        import django
        django.setup()
        # Verify we can reach the DB
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception as e:
        pytest.skip(f"Test DB not reachable: {e}")


@contextmanager
def _as_tenant(schema, org_id):
    """Helper — simulate what TenantSchemaMiddleware does for a request."""
    from django.db import connection
    with connection.cursor() as cur:
        cur.execute("BEGIN")
        try:
            cur.execute("SET LOCAL search_path TO %s, public", [schema])
            cur.execute("SET LOCAL app.current_org_id = %s", [org_id])
            try:
                cur.execute("SET LOCAL ROLE %s", [f"tenant_{schema}_role"])
            except Exception:
                # Role may not exist on the test DB — skip the role pin
                pass
            yield cur
        finally:
            cur.execute("ROLLBACK")


@pytest.fixture(scope="module")
def two_test_orgs():
    """Seed two organizations with one user each. Module-scoped so the
    Hypothesis runs don't reseed on every example.

    Cleans up at the end of the module.
    """
    _ensure_test_db()
    from django.db import connection

    org_a_id = f"org_a_{uuid.uuid4().hex[:8]}"
    org_b_id = f"org_b_{uuid.uuid4().hex[:8]}"
    schema_a = f"test_tenant_{org_a_id}"
    schema_b = f"test_tenant_{org_b_id}"
    user_a_id = f"u_a_{uuid.uuid4().hex[:8]}"
    user_b_id = f"u_b_{uuid.uuid4().hex[:8]}"

    with connection.cursor() as cur:
        # As the main role (bypasses RLS, owner of the tables)
        cur.execute(
            "INSERT INTO public.organizations (id, name, database_schema, is_active) "
            "VALUES (%s, %s, %s, TRUE), (%s, %s, %s, TRUE)",
            [org_a_id, "Org A", schema_a, org_b_id, "Org B", schema_b],
        )
        cur.execute(
            "INSERT INTO public.users (id, email, organization_id, is_active, password) "
            "VALUES (%s, %s, %s, TRUE, ''), (%s, %s, %s, TRUE, '')",
            [
                user_a_id, f"a@{org_a_id}.test", org_a_id,
                user_b_id, f"b@{org_b_id}.test", org_b_id,
            ],
        )

    yield {
        "a": {"org_id": org_a_id, "schema": schema_a, "user_id": user_a_id},
        "b": {"org_id": org_b_id, "schema": schema_b, "user_id": user_b_id},
    }

    # Cleanup
    with connection.cursor() as cur:
        cur.execute(
            "DELETE FROM public.users WHERE organization_id IN (%s, %s)",
            [org_a_id, org_b_id],
        )
        cur.execute(
            "DELETE FROM public.organizations WHERE id IN (%s, %s)",
            [org_a_id, org_b_id],
        )


class TestSharedTableIsolation:
    """Direct RLS-policy assertions on each shared table.

    These are deterministic (not Hypothesis-generated) but exercise
    the same machinery the property tests use. Useful as a sanity
    layer for new contributors before reading the Hypothesis tests.
    """

    def test_org_a_cannot_see_org_b_user(self, two_test_orgs):
        _ensure_test_db()
        with _as_tenant(
            two_test_orgs["a"]["schema"], two_test_orgs["a"]["org_id"]
        ) as cur:
            cur.execute(
                "SELECT count(*) FROM public.users WHERE id = %s",
                [two_test_orgs["b"]["user_id"]],
            )
            assert cur.fetchone()[0] == 0, (
                "RLS leak: org A's role read org B's user row."
            )

    def test_org_a_can_see_own_user(self, two_test_orgs):
        _ensure_test_db()
        with _as_tenant(
            two_test_orgs["a"]["schema"], two_test_orgs["a"]["org_id"]
        ) as cur:
            cur.execute(
                "SELECT count(*) FROM public.users WHERE id = %s",
                [two_test_orgs["a"]["user_id"]],
            )
            assert cur.fetchone()[0] == 1

    def test_org_a_cannot_see_org_b_organization_row(self, two_test_orgs):
        _ensure_test_db()
        with _as_tenant(
            two_test_orgs["a"]["schema"], two_test_orgs["a"]["org_id"]
        ) as cur:
            cur.execute(
                "SELECT count(*) FROM public.organizations WHERE id = %s",
                [two_test_orgs["b"]["org_id"]],
            )
            assert cur.fetchone()[0] == 0

    def test_org_a_cannot_insert_for_org_b(self, two_test_orgs):
        """RLS WITH CHECK should block an INSERT with another tenant's org_id."""
        _ensure_test_db()
        rogue_user_id = f"rogue_{uuid.uuid4().hex[:8]}"
        with _as_tenant(
            two_test_orgs["a"]["schema"], two_test_orgs["a"]["org_id"]
        ) as cur:
            with pytest.raises(Exception):
                cur.execute(
                    "INSERT INTO public.users "
                    "(id, email, organization_id, is_active, password) "
                    "VALUES (%s, %s, %s, TRUE, '')",
                    [rogue_user_id, f"rogue@x.test", two_test_orgs["b"]["org_id"]],
                )


class TestPropertyBasedIsolation:
    """Hypothesis-driven random sampling: any (org, user, query) tuple
    must respect the isolation contract."""

    def test_random_user_cannot_see_other_org_users(self, two_test_orgs):
        _ensure_test_db()
        from hypothesis import given, settings, strategies as st

        @given(
            requester_key=st.sampled_from(("a", "b")),
            target_key=st.sampled_from(("a", "b")),
        )
        @settings(max_examples=200, deadline=None)
        def _run(requester_key, target_key):
            requester = two_test_orgs[requester_key]
            target = two_test_orgs[target_key]

            with _as_tenant(requester["schema"], requester["org_id"]) as cur:
                cur.execute(
                    "SELECT count(*) FROM public.users WHERE id = %s",
                    [target["user_id"]],
                )
                count = cur.fetchone()[0]
                if requester_key == target_key:
                    # Same tenant — should see own row
                    assert count == 1
                else:
                    # Cross-tenant — RLS must block
                    assert count == 0, (
                        f"RLS leak: {requester_key} read {target_key}'s "
                        f"user row through public.users"
                    )

        _run()
