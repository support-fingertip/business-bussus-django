# db_utils.py
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
from django.db import connection, transaction
from django.db.utils import (
    DataError, IntegrityError, OperationalError, ProgrammingError,
)
from psycopg2 import errorcodes as PG
from psycopg2.sql import Composed
import re

SQLLike = Union[str, Composed]

@contextmanager
def safe_cursor():
    """
    Yields a fresh cursor. If an exception occurs, rollback is guaranteed.
    """
    try:
        cur = connection.cursor()
        try:
            yield cur
        finally:
            cur.close()
    except Exception:
        # Reset bad transaction state so future operations can proceed.
        try:
            connection.rollback()
        except Exception:
            pass
        raise

def _get_root_db_error(ex: Exception) -> Exception:
    # Django wraps psycopg2 exceptions; the underlying error is usually in __cause__
    return getattr(ex, "__cause__", None) or ex

def _read_diag(psycopg_err) -> Dict[str, Optional[str]]:
    d = getattr(psycopg_err, "diag", None)
    if not d:
        return {}
    return {
        "schema": getattr(d, "schema_name", None),
        "table": getattr(d, "table_name", None),
        "constraint": getattr(d, "constraint_name", None),
        "column": getattr(d, "column_name", None),
        "datatype": getattr(d, "datatype_name", None),
        "detail": getattr(d, "detail", None),
        "hint": getattr(d, "hint", None),
        "context": getattr(d, "context", None),
    }

def _constraint_columns(schema: str, constraint_name: str) -> List[str]:
    q = """
    SELECT kcu.column_name
    FROM information_schema.key_column_usage kcu
    WHERE kcu.constraint_schema = %s
      AND kcu.constraint_name = %s
    ORDER BY kcu.ordinal_position
    """
    with safe_cursor() as cur:
        cur.execute(q, [schema, constraint_name])
        return [r[0] for r in cur.fetchall()]

def _constraint_def(schema: str, constraint_name: str) -> Optional[str]:
    q = """
    SELECT pg_get_constraintdef(pc.oid, true)
    FROM pg_constraint pc
    JOIN pg_namespace pn ON pn.oid = pc.connamespace
    WHERE pn.nspname = %s AND pc.conname = %s
    """
    with safe_cursor() as cur:
        cur.execute(q, [schema, constraint_name])
        row = cur.fetchone()
        return row[0] if row else None

def explain_db_error(ex: Exception) -> Dict[str, Any]:
    """
    Convert psycopg2/Django DB errors to a clean, end-user-friendly dict.
    Covers SELECT/INSERT/UPDATE/DELETE scenarios.
    """
    psy = _get_root_db_error(ex)
    pgcode = getattr(psy, "pgcode", None)
    diag = _read_diag(psy)

    out: Dict[str, Any] = {
        "type": "database_error",
        "code": pgcode,
        "message": "Something went wrong while processing your request.",
        "field": diag.get("column"),
        "fields": [],
        "constraint": diag.get("constraint"),
        "table": diag.get("table"),
        "schema": diag.get("schema"),
        "detail": diag.get("detail"),
        "hint": diag.get("hint"),
        "context": diag.get("context"),
    }

    # ---- Integrity & Validation family
    if pgcode == PG.UNIQUE_VIOLATION:  # 23505
        cols = []
        if diag.get("constraint") and diag.get("schema"):
            try:
                cols = _constraint_columns(diag["schema"], diag["constraint"])
            except Exception:
                pass
        out.update({"type": "unique_violation", "fields": cols})
        # Try to surface the conflicting (col, value)
        msg = "A record with the same value already exists."
        if out["detail"]:
            m = re.search(r"\(([^)]+)\)=\(([^)]+)\)", out["detail"])
            if m:
                col, val = m.group(1), m.group(2)
                msg = f"{col.capitalize()} ‘{val}’ is already taken."
                if not cols:
                    out["fields"] = [col]
        elif cols:
            msg = f"{', '.join(cols).capitalize()} must be unique."
        out["message"] = msg

    elif pgcode == PG.NOT_NULL_VIOLATION:  # 23502
        out.update({"type": "not_null_violation"})
        col = diag.get("column")
        out["message"] = f"‘{col}’ is required." if col else "A required field is missing."

    elif pgcode == PG.FOREIGN_KEY_VIOLATION:  # 23503
        cols = []
        if diag.get("constraint") and diag.get("schema"):
            try:
                cols = _constraint_columns(diag["schema"], diag["constraint"])
            except Exception:
                pass
        out.update({"type": "foreign_key_violation", "fields": cols})
        out["message"] = f"Invalid reference in: {', '.join(cols)}." if cols else \
                         "This record refers to something that doesn’t exist."
                         
    elif pgcode == PG.CHECK_VIOLATION:  # 23514
        expr = None
        if diag.get("constraint") and diag.get("schema"):
            try:
                expr = _constraint_def(diag["schema"], diag["constraint"])
            except Exception:
                pass
        out.update({"type": "check_violation"})
        if 'email' in diag.get("constraint"):
            out["message"] = f"Invalid email."
        elif 'phone' in diag.get('constraint'):
            out["message"] = 'Invalid phone number'
        else:        
            out["message"] = f"Value violates rule: {expr}" if expr else \
                            "One or more values don’t meet allowed rules."

    elif pgcode == PG.EXCLUSION_VIOLATION:  # 23P01
        out.update({"type": "exclusion_violation"})
        out["message"] = "This change conflicts with existing data."

    # ---- Data type / format family
    elif pgcode == PG.STRING_DATA_RIGHT_TRUNCATION:  # 22001
        out.update({"type": "string_too_long"})
        col = diag.get("column")
        out["message"] = f"‘{col}’ is too long." if col else "One of the text fields is too long."

    elif pgcode == PG.NUMERIC_VALUE_OUT_OF_RANGE:  # 22003
        out.update({"type": "number_out_of_range"})
        col = diag.get("column")
        out["message"] = f"‘{col}’ is outside the allowed range." if col else \
                         "A number is outside the allowed range."

    elif pgcode == PG.INVALID_TEXT_REPRESENTATION:  # 22P02
        out.update({"type": "invalid_format"})
        col = diag.get("column")
        m = re.search(r'invalid input syntax for type (\w+):\s*"([^"]*)"', str(psy), re.IGNORECASE)
        if m:
            dtype, bad_val = m.group(1), m.group(2)
            out["message"] = f"'{col}' has an invalid format (got '{bad_val}')." if col else f"Invalid value '{bad_val}' for type {dtype}."
        elif col:
            out["message"] = f"'{col}' has an invalid format."
        else:
            out["message"] = "One of the values has an invalid format."

    elif pgcode == PG.DATETIME_FIELD_OVERFLOW:  # 22008
        out.update({"type": "invalid_datetime"})
        out["message"] = "One of the date/time values is invalid."

    elif isinstance(ex, DataError):
        out.update({"type": "data_error", "message": "One of the values is invalid."})

    # ---- Programming / query structure (SELECT/UPDATE/DELETE common)
    elif pgcode == PG.UNDEFINED_TABLE:  # 42P01
        out.update({"type": "undefined_table"})
        out["message"] = "The requested data source is not available."

    elif pgcode == PG.UNDEFINED_COLUMN:  # 42703
        out.update({"type": "undefined_column"})
        out["message"] = "One of the referenced fields does not exist."

    elif pgcode == PG.SYNTAX_ERROR:  # 42601
        out.update({"type": "syntax_error"})
        out["message"] = "There’s a problem with the database query."

    elif pgcode == PG.WRONG_OBJECT_TYPE:  # 42809
        out.update({"type": "wrong_object_type"})
        out["message"] = "The operation targets an object of the wrong type."

    elif isinstance(ex, ProgrammingError):
        out.update({"type": "programming_error",
                    "message": "There’s a problem with the database query."})

    # ---- Concurrency / locking / transaction
    elif pgcode == PG.LOCK_NOT_AVAILABLE:  # 55P03
        out.update({"type": "lock_not_available",
                    "message": "The data is busy. Please try again."})

    elif pgcode == PG.SERIALIZATION_FAILURE:  # 40001
        out.update({"type": "serialization_failure",
                    "message": "Your change conflicted with a concurrent update. Please retry."})

    elif pgcode == PG.DEADLOCK_DETECTED:  # 40P01
        out.update({"type": "deadlock",
                    "message": "The system hit a deadlock. Please retry."})

    elif pgcode == "57014":  # 57014
        out.update({"type": "timeout",
                    "message": "The database took too long to respond. Please try again."})

    elif isinstance(ex, OperationalError):
        out.update({"type": "operational_error",
                    "message": "A temporary database issue occurred. Please try again."})

    # ---- Privileges
    elif pgcode == PG.INSUFFICIENT_PRIVILEGE:  # 42501
        out.update({"type": "insufficient_privilege",
                    "message": "You don’t have permission to perform this action."})

    # ---- Catch-all Integrity
    elif isinstance(ex, IntegrityError):
        out.update({"type": "integrity_error",
                    "message": "This change would violate data rules."})

    return out

# ---------- Unified execution helpers (SELECT / INSERT / UPDATE / DELETE)

def run_select(
    query: SQLLike,
    params: Optional[Sequence[Any]] = None,
    *,
    fetch: str = "all",  # "all" | "one" | "val"
) -> Dict[str, Any]:
    """
    Safe SELECT runner. Returns {"success": True, "data": ..., "rows": n} or {"success": False, "error": {...}}
    fetch="all" -> list of dicts
    fetch="one" -> single dict or None
    fetch="val" -> first column value or None
    """
    try:
        with safe_cursor() as cur:
            cur.execute(query, params or [])
            cols = [c[0] for c in cur.description] if cur.description else []

            if fetch == "val":
                row = cur.fetchone()
                return {"success": True, "data": row[0] if row else None, "rows": 0 if row is None else 1}

            if fetch == "one":
                row = cur.fetchone()
                rec = dict(zip(cols, row)) if row else None
                return {"success": True, "data": rec, "rows": 0 if row is None else 1}

            # default: "all"
            rows = cur.fetchall()
            data = [dict(zip(cols, r)) for r in rows]
            return {"success": True, "data": data, "rows": len(data)}

    except Exception as e:
        try:
            connection.rollback()
        except Exception:
            pass
        return {"success": False, "error": explain_db_error(e)}

def run_write(
    query: SQLLike,
    params: Optional[Sequence[Any]] = None,
    *,
    returning: bool = False,
    fetch: str = "all",  # if returning: "all" | "one"
) -> Dict[str, Any]:
    """
    Safe INSERT/UPDATE/DELETE runner.
    - returning=False: returns {"success": True, "rows": rowcount}
    - returning=True: returns rows like run_select (dicts), plus "rows"
    """
    try:
        with safe_cursor() as cur:
            cur.execute(query, params or [])

            if returning and cur.description:
                cols = [c[0] for c in cur.description]
                if fetch == "one":
                    row = cur.fetchone()
                    rec = dict(zip(cols, row)) if row else None
                    connection.commit()
                    return {"success": True, "data": rec, "rows": 0 if row is None else 1}
                rows = cur.fetchall()
                data = [dict(zip(cols, r)) for r in rows]
                connection.commit()
                return {"success": True, "data": data, "rows": len(data)}

            affected = cur.rowcount
            connection.commit()
            return {"success": True, "rows": affected}

    except Exception as e:
        try:
            connection.rollback()
        except Exception:
            pass
        return {"success": False, "error": explain_db_error(e)}
