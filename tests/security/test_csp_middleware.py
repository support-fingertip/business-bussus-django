"""Tests for ContentSecurityPolicyMiddleware — Phase C7."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


pytestmark = pytest.mark.unit


def _ensure_django():
    pytest.importorskip("django")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "version2.settings")
    try:
        import django
        django.setup()
    except Exception:
        pytest.skip("Django not configured in this environment")


def _run(env: dict):
    """Run the middleware with a given env, return the response dict."""
    _ensure_django()
    from api.security.csp import ContentSecurityPolicyMiddleware

    mw = ContentSecurityPolicyMiddleware(get_response=lambda r: r)
    response: dict = {}
    with patch.dict(os.environ, env, clear=False):
        # Remove keys not in env so each test is isolated
        for k in ("CSP_ENFORCE", "CSP_POLICY", "CSP_REPORT_URI"):
            if k not in env:
                os.environ.pop(k, None)
        mw.process_response(MagicMock(), response)
    return response


class TestReportOnlyByDefault:
    def test_default_is_report_only(self):
        resp = _run({})
        assert "Content-Security-Policy-Report-Only" in resp
        assert "Content-Security-Policy" not in resp

    def test_default_policy_has_safe_directives(self):
        resp = _run({})
        policy = resp["Content-Security-Policy-Report-Only"]
        assert "default-src 'self'" in policy
        assert "frame-ancestors 'none'" in policy
        assert "object-src 'none'" in policy


class TestEnforceMode:
    def test_csp_enforce_sets_enforcing_header(self):
        resp = _run({"CSP_ENFORCE": "1"})
        assert "Content-Security-Policy" in resp
        assert "Content-Security-Policy-Report-Only" not in resp


class TestReportUri:
    def test_report_uri_appended_when_set(self):
        resp = _run({"CSP_REPORT_URI": "https://example.com/csp"})
        policy = resp["Content-Security-Policy-Report-Only"]
        assert "report-uri https://example.com/csp" in policy


class TestPolicyOverride:
    def test_csp_policy_env_overrides_whole_string(self):
        resp = _run({"CSP_POLICY": "default-src 'none'"})
        policy = resp["Content-Security-Policy-Report-Only"]
        assert policy.startswith("default-src 'none'")


class TestDoesNotClobber:
    def test_existing_csp_header_is_preserved(self):
        _ensure_django()
        from api.security.csp import ContentSecurityPolicyMiddleware

        mw = ContentSecurityPolicyMiddleware(get_response=lambda r: r)
        response = {"Content-Security-Policy": "default-src 'self' custom"}
        mw.process_response(MagicMock(), response)
        # A view that set its own CSP must not be overwritten.
        assert response["Content-Security-Policy"] == "default-src 'self' custom"
