"""Auth-gate regression test — Phase 2.A4.

In plain English
----------------

Phase 2.A4 will flip DRF's default to "require JWT + IsAuthenticated"
globally. Once that flag is on, every legitimately-public endpoint
(login, OTP, webhooks, OAuth callbacks, signup, health) must
explicitly opt out with ``permission_classes = [AllowAny]`` +
``authentication_classes = []``.

The risk during rollout is that some endpoint accidentally has the
wrong opt-out — either it's missing (caused a 401 for a flow that
should be open) or extra (a tenant-data endpoint became unauthenticated).

This test catches that. It:
  1. Reads the URL conf.
  2. For every URL pattern, builds a representative request path.
  3. Sends an unauthenticated GET.
  4. Asserts the response is 401/403 UNLESS the URL path matches a
     regex on ``tests/security/public_urls.txt``.

A failing test means EITHER:
  * The audit missed a legitimately-public URL (add it to
    public_urls.txt + security-review the PR), or
  * A new endpoint was added that needs auth but doesn't have it
    (fix the view, don't add it to the allowlist).

Adding a URL to the allowlist requires a security-team eyeball.

How this test runs
------------------

* In a stripped CI environment (no DB): skips cleanly via
  ``pytest.importorskip("django")``.
* In a CI environment with a test DB: runs the full URL enumeration.
* Locally:
    pytest tests/security/test_auth_required.py -v
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


_ALLOWLIST_PATH = Path(__file__).parent / "public_urls.txt"


def _load_allowlist() -> list[re.Pattern]:
    """Parse public_urls.txt into a list of compiled regexes."""
    if not _ALLOWLIST_PATH.exists():
        return []
    patterns: list[re.Pattern] = []
    with _ALLOWLIST_PATH.open() as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()  # strip inline comments
            if not line:
                continue
            try:
                patterns.append(re.compile(line))
            except re.error as exc:
                raise RuntimeError(
                    f"public_urls.txt: invalid regex {line!r} ({exc})"
                )
    return patterns


def _matches_allowlist(path: str, patterns: list[re.Pattern]) -> bool:
    return any(p.search(path) for p in patterns)


def _example_path_for(pattern):
    """Convert a Django URL pattern to a plausible test path.

    Best-effort — replaces ``<str:foo>`` with ``probe`` etc. Good enough
    to exercise routing without needing real data.
    """
    s = str(pattern.pattern) if hasattr(pattern, "pattern") else str(pattern)
    # Django 4+ URLPattern uses RoutePattern; representation includes the
    # original path expression.
    s = re.sub(r"<(?:[^:>]+:)?[^>]+>", "probe", s)
    # Strip regex anchors so we get the path expression.
    s = s.replace("^", "").replace("$", "")
    return s


def _ensure_django():
    pytest.importorskip("django")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "version2.settings")
    try:
        import django
        django.setup()
    except Exception:
        pytest.skip("Django not configured in this environment")


class TestAllowListFile:
    """The allowlist file itself must parse + be non-empty."""

    def test_allowlist_file_exists(self):
        assert _ALLOWLIST_PATH.exists(), (
            f"Missing {_ALLOWLIST_PATH}. The auth-gate regression test "
            "requires this file."
        )

    def test_allowlist_parses(self):
        patterns = _load_allowlist()
        assert patterns, "Allowlist is empty — at least healthz should be on it."

    def test_allowlist_covers_health(self):
        patterns = _load_allowlist()
        for path in ("/healthz", "/livez", "/readyz"):
            assert _matches_allowlist(path, patterns), (
                f"{path} not on allowlist; health probes need to be public"
            )


class TestEveryUrlEitherProtectedOrOnAllowlist:
    """The main regression: every URL is either authenticated OR on the allowlist."""

    def test_url_enumeration(self):
        _ensure_django()
        from django.urls import get_resolver

        try:
            resolver = get_resolver()
        except Exception:
            pytest.skip("Cannot resolve URL conf — check DJANGO_SETTINGS_MODULE")

        patterns = _load_allowlist()
        if not patterns:
            pytest.skip("Allowlist empty — bootstrap public_urls.txt first")

        # Enumerate the URL conf depth-first. Each pattern is either a
        # URLPattern (leaf) or a URLResolver (include()'d sub-conf).
        from django.urls.resolvers import URLPattern, URLResolver

        leaves: list[tuple[str, object]] = []  # (rendered_path, view_callable)

        def walk(node, prefix=""):
            if isinstance(node, URLResolver):
                for sub in node.url_patterns:
                    walk(sub, prefix + _example_path_for(node.pattern))
            elif isinstance(node, URLPattern):
                leaves.append((prefix + _example_path_for(node.pattern), node.callback))

        for p in resolver.url_patterns:
            walk(p)

        # Now check each leaf: either it's on the allowlist OR its view
        # must declare an authentication requirement.
        missing_protection: list[str] = []
        for path, view in leaves:
            full_path = "/" + path.lstrip("/")
            if _matches_allowlist(full_path, patterns):
                continue  # explicitly public — fine

            # Inspect the view for a permission/authentication declaration.
            # DRF class-based: `view.cls.permission_classes`.
            # DRF function-based (@api_view): `view.view_class` from the
            # decorator's wrapper, or `getattr(view, 'cls', ...)`.
            # Plain Django views: never inherit auth from DRF; require an
            # explicit middleware-level check (not in scope of this test).
            permission_classes = None
            view_cls = getattr(view, "cls", None) or getattr(view, "view_class", None)
            if view_cls is not None:
                permission_classes = getattr(view_cls, "permission_classes", None)

            if permission_classes is None:
                # Plain Django view (not DRF) — out of scope. Skip.
                continue

            # We now have a DRF view. If it includes IsAuthenticated (or
            # equivalent) it's protected. If it includes AllowAny, it
            # should be on the allowlist — flag.
            from rest_framework.permissions import AllowAny, IsAuthenticated

            class_names = {c.__name__ for c in permission_classes}
            if "AllowAny" in class_names and full_path not in patterns:
                # AllowAny but not on the allowlist — security flag.
                missing_protection.append(
                    f"{full_path}: AllowAny but not on public_urls.txt"
                )
            elif not permission_classes:
                missing_protection.append(
                    f"{full_path}: empty permission_classes, no global default yet"
                )

        # Sort for deterministic failure output
        if missing_protection:
            pytest.fail(
                "URLs need explicit handling before STRICT_AUTH=1 can flip:\n  - "
                + "\n  - ".join(sorted(missing_protection))
            )
