"""Tests for the statement-timeout middleware (path → bucket logic)."""

from __future__ import annotations

import pytest

from api.security.statement_timeout import _bucket_ms, DEFAULT_MS, EXPORT_MS, REPORT_MS


pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/v2/api/leads", DEFAULT_MS),
        ("/v2/api/listview", DEFAULT_MS),
        ("/", DEFAULT_MS),
        ("", DEFAULT_MS),
        ("/v2/api/report/abc", REPORT_MS),
        ("/v2/api/dashboard/widget", REPORT_MS),
        ("/export/csv", EXPORT_MS),
        ("/export", EXPORT_MS),
        ("/v2/api/data_export/run", EXPORT_MS),
    ],
)
def test_path_routes_to_correct_bucket(path, expected):
    assert _bucket_ms(path) == expected
