"""Configuration loader for the API smoke-test suite.

Resolution order (highest priority first):
  1. CLI flags (handled by run_tests.py, not here)
  2. Environment variables
  3. JSON config file (default: ./config.json next to run_tests.py)
  4. Built-in defaults
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any


@dataclass
class Config:
    base_url: str = "http://localhost:8000"
    frontend_url: str = ""

    # existing user the tests log in as
    test_username: str = ""
    test_password: str = ""

    # admin login (optional)
    admin_username: str = ""
    admin_password: str = ""

    # new user the create-user suite provisions
    new_user_email_prefix: str = "qa.testuser"
    new_user_email_domain: str = "example.com"
    new_user_password: str = "TempPass!2345"
    new_user_profile_id: str = ""

    # crud probe
    crud_object: str = "task"
    crud_create_payload: dict = field(default_factory=lambda: {
        "subject": "API smoke test",
        "status": "Open",
        "priority": "Low",
    })
    crud_update_payload: dict = field(default_factory=lambda: {
        "subject": "API smoke test (updated)",
        "priority": "High",
    })

    suites: list[str] = field(default_factory=lambda: ["all"])
    stop_on_failure: bool = False
    verbose: bool = False
    keep_created: bool = False
    timeout: int = 30
    log_dir: str = "./logs"
    report_json: str = ""

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        cfg = cls()
        if path and path.exists():
            cfg._merge_dict(json.loads(path.read_text()))
        cfg._merge_env()
        return cfg

    # ----- merge helpers -----

    def _merge_dict(self, data: dict[str, Any]) -> None:
        valid = {f.name for f in fields(self)}
        for key, value in data.items():
            k = key.lower()
            if k in valid and value is not None:
                setattr(self, k, value)

    def _merge_env(self) -> None:
        env_map = {
            "BASE_URL": ("base_url", str),
            "FRONTEND_URL": ("frontend_url", str),
            "TEST_USERNAME": ("test_username", str),
            "TEST_PASSWORD": ("test_password", str),
            "ADMIN_USERNAME": ("admin_username", str),
            "ADMIN_PASSWORD": ("admin_password", str),
            "NEW_USER_EMAIL_PREFIX": ("new_user_email_prefix", str),
            "NEW_USER_EMAIL_DOMAIN": ("new_user_email_domain", str),
            "NEW_USER_PASSWORD": ("new_user_password", str),
            "NEW_USER_PROFILE_ID": ("new_user_profile_id", str),
            "CRUD_OBJECT": ("crud_object", str),
            "CRUD_CREATE_PAYLOAD": ("crud_create_payload", "json"),
            "CRUD_UPDATE_PAYLOAD": ("crud_update_payload", "json"),
            "SUITES": ("suites", "csv"),
            "STOP_ON_FAILURE": ("stop_on_failure", "bool"),
            "VERBOSE": ("verbose", "bool"),
            "KEEP_CREATED": ("keep_created", "bool"),
            "HTTP_TIMEOUT": ("timeout", int),
            "LOG_DIR": ("log_dir", str),
            "REPORT_JSON": ("report_json", str),
        }
        for env_key, (attr, kind) in env_map.items():
            raw = os.environ.get(env_key)
            if raw is None or raw == "":
                continue
            if kind == "json":
                try:
                    setattr(self, attr, json.loads(raw))
                except json.JSONDecodeError:
                    raise SystemExit(f"{env_key} is not valid JSON: {raw!r}")
            elif kind == "csv":
                setattr(self, attr, [s.strip() for s in raw.split(",") if s.strip()])
            elif kind == "bool":
                setattr(self, attr, raw.strip().lower() in ("1", "true", "yes", "on"))
            elif kind is int:
                setattr(self, attr, int(raw))
            else:
                setattr(self, attr, raw)

    # ----- introspection -----

    def selected_suites(self, all_suites: list[str]) -> list[str]:
        if not self.suites or "all" in [s.lower() for s in self.suites]:
            return list(all_suites)
        wanted = {s.lower() for s in self.suites}
        return [s for s in all_suites if s in wanted]

    def redact(self) -> dict:
        """Return a dict suitable for logging — passwords removed."""
        d = {f.name: getattr(self, f.name) for f in fields(self)}
        for k in ("test_password", "admin_password", "new_user_password"):
            if d.get(k):
                d[k] = "***"
        return d
