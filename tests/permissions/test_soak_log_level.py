"""Tests for the SOAK_LOG_LEVEL knob on the dispatch helper.

The knob promotes the per-call dispatch log lines from DEBUG (default)
to INFO (during an active soak) without flipping the application's
overall log level. Operators set ``SOAK_LOG_LEVEL=INFO`` per the
runbook at ``docs/SOAK_RUNBOOK.md``.

Tests cover the level-resolution helper directly (no monkeypatching of
the logger needed) plus a behavioural check that the dispatch path
emits at the resolved level.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest


pytestmark = pytest.mark.unit


class TestSoakLogLevelResolution:
    """``_soak_log_level`` reads the env var and returns a stdlib level int."""

    def test_default_is_debug(self, monkeypatch):
        from api.permissions._orm_dispatch import _soak_log_level
        monkeypatch.delenv("SOAK_LOG_LEVEL", raising=False)
        assert _soak_log_level() == logging.DEBUG

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("DEBUG", logging.DEBUG),
            ("INFO", logging.INFO),
            ("WARNING", logging.WARNING),
            ("ERROR", logging.ERROR),
            ("CRITICAL", logging.CRITICAL),
        ],
    )
    def test_recognised_level_names(self, monkeypatch, value, expected):
        from api.permissions._orm_dispatch import _soak_log_level
        monkeypatch.setenv("SOAK_LOG_LEVEL", value)
        assert _soak_log_level() == expected

    def test_lowercase_is_normalised(self, monkeypatch):
        from api.permissions._orm_dispatch import _soak_log_level
        monkeypatch.setenv("SOAK_LOG_LEVEL", "info")
        assert _soak_log_level() == logging.INFO

    def test_whitespace_is_stripped(self, monkeypatch):
        from api.permissions._orm_dispatch import _soak_log_level
        monkeypatch.setenv("SOAK_LOG_LEVEL", "  INFO  ")
        assert _soak_log_level() == logging.INFO

    @pytest.mark.parametrize("value", ["GARBAGE", "", "TRACE", "0"])
    def test_invalid_falls_back_to_debug(self, monkeypatch, value):
        """A misconfigured env var must NOT break dispatch — silent
        fallback to DEBUG keeps requests serving."""
        from api.permissions._orm_dispatch import _soak_log_level
        monkeypatch.setenv("SOAK_LOG_LEVEL", value)
        assert _soak_log_level() == logging.DEBUG


class TestDispatchEmitsAtResolvedLevel:
    """``dispatch`` itself logs at the level returned by
    ``_soak_log_level``. Use a captured handler on the dispatch
    module's logger to verify the emitted level."""

    def _capture_at(self, level):
        """Return a handler that records every record at or above ``level``."""
        from api.permissions._orm_dispatch import logger

        handler = logging.Handler()
        handler.setLevel(level)
        captured: list[logging.LogRecord] = []
        handler.emit = lambda record: captured.append(record)  # type: ignore[assignment]
        logger.addHandler(handler)
        previous = logger.level
        logger.setLevel(level)
        return logger, handler, captured, previous

    def test_default_emits_at_debug(self, monkeypatch):
        from api.permissions._orm_dispatch import dispatch
        monkeypatch.delenv("SOAK_LOG_LEVEL", raising=False)
        monkeypatch.delenv("USE_ORM_FOR_PERMISSIONS", raising=False)

        logger, handler, captured, previous = self._capture_at(logging.DEBUG)
        try:
            dispatch("test", lambda: "raw", lambda: "orm")
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous)

        assert len(captured) == 1
        assert captured[0].levelno == logging.DEBUG

    def test_promoted_emits_at_info(self, monkeypatch):
        from api.permissions._orm_dispatch import dispatch
        monkeypatch.setenv("SOAK_LOG_LEVEL", "INFO")
        monkeypatch.delenv("USE_ORM_FOR_PERMISSIONS", raising=False)

        logger, handler, captured, previous = self._capture_at(logging.INFO)
        try:
            dispatch("test", lambda: "raw", lambda: "orm")
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous)

        assert len(captured) == 1
        assert captured[0].levelno == logging.INFO

    def test_log_message_contains_flag_and_path(self, monkeypatch):
        from api.permissions._orm_dispatch import dispatch
        monkeypatch.setenv("SOAK_LOG_LEVEL", "INFO")
        monkeypatch.setenv("USE_DYNAMIC_GATEWAY", "1")
        monkeypatch.delenv("USE_ORM_FOR_PERMISSIONS", raising=False)

        logger, handler, captured, previous = self._capture_at(logging.INFO)
        try:
            dispatch(
                "deleteSQLFunction.delete_data_sql.leads",
                lambda: "raw",
                lambda: "orm",
                flag="USE_DYNAMIC_GATEWAY",
            )
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous)

        assert len(captured) == 1
        msg = captured[0].getMessage()
        assert "USE_DYNAMIC_GATEWAY" in msg
        assert "deleteSQLFunction.delete_data_sql.leads" in msg
        assert "ORM path" in msg
