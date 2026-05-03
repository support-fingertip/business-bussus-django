#!/usr/bin/env python3
"""End-to-end API smoke-test runner for the Bussus backend.

Usage:
  python run_tests.py [--config config.json] [--suite auth,users,...] [--verbose]

Returns a non-zero exit status when any test fails.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

# Allow `python run_tests.py` to work whether run from this dir or from the repo root.
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from client import TestClient, TestReport  # noqa: E402
from config import Config  # noqa: E402
from suites import REGISTRY, ORDERED_SUITES  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bussus backend API smoke-test runner")
    p.add_argument("--config", type=Path, default=HERE / "config.json",
                   help="Path to JSON config file (default: ./config.json)")
    p.add_argument("--base-url", help="Override base URL")
    p.add_argument("--username", help="Override TEST_USERNAME")
    p.add_argument("--password", help="Override TEST_PASSWORD")
    p.add_argument("--suite", help="Comma-separated suites to run "
                                   f"(or 'all'). Available: {','.join(ORDERED_SUITES)}")
    p.add_argument("--verbose", action="store_true", help="Print per-request lines")
    p.add_argument("--stop-on-failure", action="store_true",
                   help="Abort the run on the first failed assertion")
    p.add_argument("--keep-created", action="store_true",
                   help="Don't clean up users/records the suites create")
    p.add_argument("--report-json", help="Write a structured JSON report to this path")
    p.add_argument("--list-suites", action="store_true",
                   help="Print available suites and exit")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.list_suites:
        for s in ORDERED_SUITES:
            print(s)
        return 0

    config = Config.load(args.config)
    # CLI overrides win
    if args.base_url:    config.base_url = args.base_url
    if args.username:    config.test_username = args.username
    if args.password:    config.test_password = args.password
    if args.suite:       config.suites = [s.strip() for s in args.suite.split(",") if s.strip()]
    if args.verbose:     config.verbose = True
    if args.stop_on_failure: config.stop_on_failure = True
    if args.keep_created:    config.keep_created = True
    if args.report_json:     config.report_json = args.report_json

    log_dir = Path(config.log_dir).expanduser().resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    log_path = log_dir / f"api_test_{timestamp}.log"

    report = TestReport(stop_on_failure=config.stop_on_failure)
    client = TestClient(
        base_url=config.base_url,
        report=report,
        log_path=log_path,
        frontend_url=config.frontend_url,
        timeout=config.timeout,
        verbose=config.verbose,
    )

    # Header
    print(client.color.bold("Bussus API smoke-test runner"))
    print(f"  base_url: {config.base_url}")
    print(f"  user:     {config.test_username or '(unset)'}")
    print(f"  log:      {log_path}")
    client.logger.info("config: %s", json.dumps(config.redact(), default=str))

    selected = config.selected_suites(ORDERED_SUITES)
    if not selected:
        print(client.color.red(f"No suites selected. Available: {','.join(ORDERED_SUITES)}"))
        return 2
    print(f"  suites:   {', '.join(selected)}")

    ctx: dict = {}
    started = time.perf_counter()
    aborted = False
    for suite_name in selected:
        runner = REGISTRY.get(suite_name)
        if runner is None:
            print(client.color.red(f"Unknown suite: {suite_name}"))
            continue
        try:
            runner(client, ctx, config)
        except AssertionError as exc:
            # Raised only when stop_on_failure=True
            print(client.color.red(f"\nAborted on first failure: {exc}"))
            aborted = True
            break
        except Exception as exc:  # don't let one bad suite kill the run
            print(client.color.red(
                f"\n  Suite {suite_name!r} raised {type(exc).__name__}: {exc}"))
            client.logger.exception("suite %s crashed", suite_name)
    duration = time.perf_counter() - started

    print()
    print(client.color.bold("===== Test Summary ====="))
    print(f"  total:   {report.total}")
    print(f"  {client.color.green('passed')}:  {report.passed}")
    print(f"  {client.color.red('failed')}:  {report.failed}")
    print(f"  {client.color.yellow('skipped')}: {report.skipped}")
    print(f"  duration: {duration:.1f}s")

    if report.failed:
        print()
        print(client.color.red("Failures:"))
        for r in report.results:
            if r.status == "fail":
                loc = f"{r.method or '?'} {r.path or ''}".strip()
                print(f"  - [{r.suite}] {r.name}")
                print(f"      {client.color.dim(loc)}  →  {r.reason}")

    if config.report_json:
        out = Path(config.report_json).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "base_url": config.base_url,
            "started":  datetime.utcnow().isoformat(),
            "duration_seconds": round(duration, 3),
            "totals": {"total": report.total, "passed": report.passed,
                       "failed": report.failed, "skipped": report.skipped},
            "results": [asdict(r) for r in report.results],
        }, indent=2))
        print(f"  json report: {out}")

    print(f"  full log: {log_path}")

    if aborted or report.failed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
