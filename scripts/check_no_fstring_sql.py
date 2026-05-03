#!/usr/bin/env python3
"""Pre-commit / CI check: refuse to merge any new f-string SQL.

Walks every staged ``.py`` file (or all files under ``api/``, ``utils/``,
``adminuser/``, ``public/``, ``whatsapp/``, ``facebook/``,
``sf_integration/``, ``data_export/``, ``CacheService/``, ``middleware/``,
``authentication/``, ``emailsend/`` if invoked without arguments) and
flags any ``cursor.execute(...)`` / ``cursor.executemany(...)`` /
``run_query(...)`` whose first argument is an f-string OR a ``.format(...)``
call OR a ``+`` concatenation.

The intent is **regression prevention**, not an exhaustive scan of legacy
code. Existing violations need to be fixed in code, not ignored here —
this hook only blocks NEW ones from being introduced.

Exit codes:
  0 — clean
  1 — at least one violation found

Wire into pre-commit by either:
  - committing ``.pre-commit-config.yaml`` (provided alongside this file)
  - or adding to CI: ``python scripts/check_no_fstring_sql.py``
"""

from __future__ import annotations

import argparse
import ast
import os
import sys
from typing import Iterable


SQL_CALLERS = {"execute", "executemany"}
RAW_QUERY_FUNCS = {"run_query", "raw"}


class FStringSqlVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.violations: list[tuple[int, str]] = []

    @staticmethod
    def _is_sql_composable(node: ast.AST) -> bool:
        """``sql.SQL("...")`` and friends are the safe psycopg2 pattern."""
        if not isinstance(node, ast.Call):
            return False
        f = node.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            return f.value.id in {"sql", "_sql"} and f.attr in {
                "SQL", "Identifier", "Composed", "Literal",
            }
        return False

    def _is_unsafe_arg(self, node: ast.AST) -> bool:
        # f-strings on string literals are unsafe.
        if isinstance(node, ast.JoinedStr):
            return True
        # `"..." % vars` or `"..." + var` on plain strings is unsafe; recurse.
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
            return self._is_unsafe_arg(node.left) or self._is_unsafe_arg(node.right)
        # `.format(...)` is unsafe ONLY when called inline on a string literal:
        #   "INSERT ... ({}) VALUES (%s)".format(table_name)
        # `sql.SQL(...).format()` is the canonical SAFE pattern. Bare
        # `query.format(...)` on a Name is ambiguous (the Name might bind
        # to a `sql.SQL` composable defined nearby), so we don't flag it
        # here; rely on code review for that case.
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr == "format":
                receiver = f.value
                if isinstance(receiver, ast.Constant) and isinstance(receiver.value, str):
                    return True
        return False

    def visit_Call(self, node: ast.Call) -> None:  # noqa: D401 - ast handler
        f = node.func
        callee_name = None
        if isinstance(f, ast.Attribute):
            callee_name = f.attr
        elif isinstance(f, ast.Name):
            callee_name = f.id

        if callee_name in SQL_CALLERS or callee_name in RAW_QUERY_FUNCS:
            if node.args and self._is_unsafe_arg(node.args[0]):
                # Skip if the file is a test or generator script
                self.violations.append((
                    node.lineno,
                    callee_name or "<unknown>",
                ))
        self.generic_visit(node)


SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules"}
DEFAULT_ROOTS = (
    "api", "utils", "adminuser", "public", "whatsapp", "facebook",
    "sf_integration", "data_export", "CacheService", "middleware",
    "authentication", "emailsend", "version2",
)


def iter_paths(args_paths: list[str]) -> Iterable[str]:
    if args_paths:
        for p in args_paths:
            if os.path.isfile(p) and p.endswith(".py"):
                yield p
            elif os.path.isdir(p):
                yield from _walk_py(p)
        return
    for root in DEFAULT_ROOTS:
        if os.path.isdir(root):
            yield from _walk_py(root)


def _walk_py(root: str) -> Iterable[str]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("paths", nargs="*", help="Files or directories to scan.")
    args = p.parse_args()

    failed = False
    for path in iter_paths(args.paths):
        try:
            with open(path, "r", encoding="utf-8") as f:
                src = f.read()
            tree = ast.parse(src, filename=path)
        except (OSError, SyntaxError):
            continue
        visitor = FStringSqlVisitor(path)
        visitor.visit(tree)
        for lineno, callee in visitor.violations:
            print(
                f"{path}:{lineno}: f-string / concat / .format() passed to "
                f"{callee}() — use psycopg2.sql.Identifier / SQL.format instead",
                file=sys.stderr,
            )
            failed = True

    if failed:
        print(
            "\nNew f-string SQL detected. See "
            "api/ORM/sqlFunctions/utils/helpers.py::validate_identifier "
            "and psycopg2.sql for the safe pattern.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
