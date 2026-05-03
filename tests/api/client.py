"""HTTP client + assertion helpers for the API smoke-test suite.

The TestClient wraps `requests.Session` and:
- prepends BASE_URL to relative paths
- attaches Authorization: Bearer <token> when set_token() has been called
- attaches X-Frontend-URL when configured (some tenant-resolution paths use it)
- writes every request/response into a session log
- exposes assert_* methods that record results into a TestReport

All assert_* methods return the (possibly truncated) Result object so callers
can chain or inspect; they never raise unless `stop_on_failure=True` is set
on the report.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import requests


@dataclass
class TestResult:
    name: str
    suite: str
    status: str  # "pass" | "fail" | "skip"
    reason: str = ""
    duration_ms: int = 0
    http_status: int | None = None
    method: str | None = None
    path: str | None = None
    response_excerpt: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class TestReport:
    results: list[TestResult] = field(default_factory=list)
    stop_on_failure: bool = False
    current_suite: str = "(none)"

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == "pass")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == "fail")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == "skip")

    @property
    def total(self) -> int:
        return len(self.results)

    def record(self, result: TestResult) -> None:
        self.results.append(result)


class _Color:
    """ANSI colour helpers. Auto-disabled when stdout is not a tty."""
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        if not self.enabled:
            return text
        return f"\033[{code}m{text}\033[0m"

    def red(self, t: str) -> str:    return self._wrap("31", t)
    def green(self, t: str) -> str:  return self._wrap("32", t)
    def yellow(self, t: str) -> str: return self._wrap("33", t)
    def blue(self, t: str) -> str:   return self._wrap("34", t)
    def bold(self, t: str) -> str:   return self._wrap("1", t)
    def dim(self, t: str) -> str:    return self._wrap("2", t)


class TestClient:
    def __init__(
        self,
        base_url: str,
        report: TestReport,
        log_path: Path,
        frontend_url: str | None = None,
        timeout: int = 30,
        verbose: bool = False,
        use_color: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.frontend_url = frontend_url or ""
        self.timeout = timeout
        self.verbose = verbose
        self.report = report
        self.session = requests.Session()
        self.token: str | None = None

        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("api_test")
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()
        fh = logging.FileHandler(self.log_path, mode="w", encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        self.logger.addHandler(fh)

        # printed metadata for the most recent request
        self._last_status: int | None = None
        self._last_body_text: str = ""
        self._last_json: Any = None
        self._last_method: str | None = None
        self._last_path: str | None = None
        self._last_duration_ms: int = 0

        import sys
        self.color = _Color(use_color and sys.stdout.isatty())

    # ----- session config -----

    def set_token(self, token: str | None) -> None:
        self.token = token

    def set_suite(self, name: str) -> None:
        self.report.current_suite = name
        self.logger.info("=== suite: %s ===", name)
        print()
        print(self.color.bold(self.color.blue(f"== {name} ==")))

    # ----- HTTP -----

    def request(
        self,
        method: str,
        path: str,
        json_body: Any = None,
        params: dict | None = None,
        anonymous: bool = False,
        extra_headers: dict | None = None,
    ) -> "TestClient":
        """Issue an HTTP request. Returns self so callers can chain assertions."""
        if path.startswith(("http://", "https://")):
            url = path
        else:
            url = f"{self.base_url}{path}"

        headers: dict[str, str] = {"Accept": "application/json"}
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        if not anonymous and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.frontend_url:
            headers["X-Frontend-URL"] = self.frontend_url
        if extra_headers:
            headers.update(extra_headers)

        body_data = None
        if json_body is not None:
            body_data = json.dumps(json_body)

        started = time.perf_counter()
        try:
            resp = self.session.request(
                method=method.upper(),
                url=url,
                data=body_data,
                params=params,
                headers=headers,
                timeout=self.timeout,
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            self._last_status = resp.status_code
            self._last_body_text = resp.text
            try:
                self._last_json = resp.json()
            except ValueError:
                self._last_json = None
        except requests.RequestException as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            self._last_status = 0
            self._last_body_text = f"<network error: {exc}>"
            self._last_json = None

        self._last_method = method.upper()
        self._last_path = path
        self._last_duration_ms = duration_ms

        self.logger.info(
            "%s %s -> %s (%dms)",
            method.upper(), url, self._last_status, duration_ms,
        )
        if json_body is not None:
            self.logger.debug("request body: %s", json.dumps(json_body)[:2000])
        self.logger.debug("response body: %s", self._last_body_text[:2000])

        if self.verbose:
            print(self.color.dim(
                f"  -> {method.upper()} {path} "
                f"[{self._last_status}] in {duration_ms}ms"
            ))
        return self

    # convenience
    def get(self, path: str, **kw):    return self.request("GET",    path, **kw)
    def post(self, path: str, **kw):   return self.request("POST",   path, **kw)
    def patch(self, path: str, **kw):  return self.request("PATCH",  path, **kw)
    def put(self, path: str, **kw):    return self.request("PUT",    path, **kw)
    def delete(self, path: str, **kw): return self.request("DELETE", path, **kw)

    # ----- response inspection -----

    @property
    def last_status(self) -> int | None:
        return self._last_status

    @property
    def last_json(self) -> Any:
        return self._last_json

    @property
    def last_body_text(self) -> str:
        return self._last_body_text

    def json_get(self, path: str, default: Any = None) -> Any:
        """Walk a dotted path through self._last_json, e.g. 'user.profile_id'.
        Returns `default` for any missing segment."""
        cur = self._last_json
        if cur is None:
            return default
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return default
        return cur

    # ----- assertions -----

    def _record(
        self,
        name: str,
        passed: bool,
        reason: str = "",
    ) -> TestResult:
        excerpt = self._last_body_text[:300] if not passed else ""
        result = TestResult(
            name=name,
            suite=self.report.current_suite,
            status="pass" if passed else "fail",
            reason=reason,
            duration_ms=self._last_duration_ms,
            http_status=self._last_status,
            method=self._last_method,
            path=self._last_path,
            response_excerpt=excerpt,
        )
        self.report.record(result)
        if passed:
            print(f"  {self.color.green('PASS')} {name} "
                  f"{self.color.dim(f'[{self._last_status} · {self._last_duration_ms}ms]')}")
            self.logger.info("PASS %s", name)
        else:
            print(f"  {self.color.red('FAIL')} {name}")
            print(f"       {self.color.dim('reason')}: {reason}")
            if excerpt:
                print(f"       {self.color.dim('body')}:   {excerpt[:240]}")
            self.logger.error("FAIL %s — %s", name, reason)
            if self._last_body_text:
                self.logger.error("response body: %s", self._last_body_text[:2000])
            if self.report.stop_on_failure:
                raise AssertionError(f"{name}: {reason}")
        return result

    def skip(self, name: str, reason: str) -> TestResult:
        result = TestResult(
            name=name,
            suite=self.report.current_suite,
            status="skip",
            reason=reason,
        )
        self.report.record(result)
        print(f"  {self.color.yellow('SKIP')} {name} "
              f"{self.color.dim(f'({reason})')}")
        self.logger.info("SKIP %s (%s)", name, reason)
        return result

    def assert_status(self, name: str, *expected: int) -> TestResult:
        ok = self._last_status in expected
        reason = "" if ok else f"expected {list(expected)}, got {self._last_status}"
        return self._record(name, ok, reason)

    def assert_status_in_range(self, name: str, low: int, high: int) -> TestResult:
        ok = self._last_status is not None and low <= self._last_status <= high
        reason = "" if ok else f"expected status in [{low},{high}], got {self._last_status}"
        return self._record(name, ok, reason)

    def assert_field(self, name: str, json_path: str) -> TestResult:
        """Pass if the dotted JSON path resolves to a non-None value."""
        val = self.json_get(json_path, default=None)
        ok = val is not None and val != ""
        reason = "" if ok else f"missing/empty field: {json_path}"
        return self._record(name, ok, reason)

    def assert_field_equals(self, name: str, json_path: str, expected: Any) -> TestResult:
        val = self.json_get(json_path)
        ok = val == expected
        reason = "" if ok else f"{json_path} expected={expected!r}, actual={val!r}"
        return self._record(name, ok, reason)

    def assert_field_type(self, name: str, json_path: str, types: type | tuple[type, ...]) -> TestResult:
        val = self.json_get(json_path)
        ok = isinstance(val, types)
        type_str = types.__name__ if isinstance(types, type) else "/".join(t.__name__ for t in types)
        reason = "" if ok else f"{json_path} not {type_str} (got {type(val).__name__})"
        return self._record(name, ok, reason)

    def assert_array_nonempty(self, name: str, json_path: str = "") -> TestResult:
        val = self._last_json if json_path == "" else self.json_get(json_path)
        ok = isinstance(val, list) and len(val) > 0
        if ok:
            reason = ""
        elif not isinstance(val, list):
            reason = f"{json_path or '<root>'} is not an array (got {type(val).__name__})"
        else:
            reason = f"{json_path or '<root>'} array is empty"
        return self._record(name, ok, reason)

    def assert_body_contains(self, name: str, needle: str) -> TestResult:
        ok = needle in self._last_body_text
        reason = "" if ok else f"body does not contain {needle!r}"
        return self._record(name, ok, reason)

    def assert_predicate(self, name: str, predicate, reason_fn=None) -> TestResult:
        """Pass when the predicate(self) returns truthy.
        `reason_fn(self)` is called only on failure to construct the message."""
        try:
            ok = bool(predicate(self))
        except Exception as exc:
            ok = False
            reason = f"predicate raised {type(exc).__name__}: {exc}"
        else:
            reason = "" if ok else (reason_fn(self) if reason_fn else "predicate returned false")
        return self._record(name, ok, reason)
