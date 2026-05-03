"""Unit tests for ``api.security.correlation``.

The middleware is exercised via direct ``process_request`` /
``process_response`` calls; we don't need the full Django test client
for the contract under test.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.security.correlation import (
    REQUEST_ID_HEADER,
    RequestContextFilter,
    RequestCorrelationMiddleware,
    RESPONSE_HEADER,
    get_trace_id,
    set_tenant_id,
    set_user_id,
)


pytestmark = pytest.mark.unit


def _fake_request(meta: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(META=(meta or {}), trace_id=None)


class TestRequestCorrelationMiddleware:
    def test_generates_trace_id_when_header_absent(self):
        mw = RequestCorrelationMiddleware(get_response=lambda r: r)
        req = _fake_request()
        mw.process_request(req)
        assert req.trace_id
        assert get_trace_id() == req.trace_id

    def test_uses_inbound_request_id_header(self):
        mw = RequestCorrelationMiddleware(get_response=lambda r: r)
        req = _fake_request({REQUEST_ID_HEADER: "abc123"})
        mw.process_request(req)
        assert req.trace_id == "abc123"

    def test_response_carries_trace_id(self):
        mw = RequestCorrelationMiddleware(get_response=lambda r: r)
        req = _fake_request()
        mw.process_request(req)
        response = {}  # dict acts like a response object: __setitem__ headers
        out = mw.process_response(req, response)
        assert out[RESPONSE_HEADER] == req.trace_id


class TestRequestContextFilter:
    def test_injects_default_dashes(self):
        # No request context active in this thread → all three are "-".
        record = make_log_record()
        filt = RequestContextFilter()
        # Reset contextvars to known empty state for this test.
        set_tenant_id(None)
        set_user_id(None)
        assert filt.filter(record) is True
        assert record.tenant_id == "-"
        assert record.user_id == "-"

    def test_injects_set_values(self):
        set_tenant_id("org_alpha_0000")
        set_user_id("usr_alpha_0001")
        record = make_log_record()
        RequestContextFilter().filter(record)
        assert record.tenant_id == "org_alpha_0000"
        assert record.user_id == "usr_alpha_0001"


def make_log_record():
    import logging
    return logging.LogRecord(
        name="t", level=logging.INFO, pathname=__file__,
        lineno=0, msg="m", args=(), exc_info=None,
    )
