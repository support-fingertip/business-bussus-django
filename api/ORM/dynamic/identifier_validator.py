"""Strict identifier validation.

Wraps ``api.ORM.sqlFunctions.utils.helpers.validate_identifier`` with
named entry points so callsites read self-explanatorily and so we can
add future per-kind rules (e.g. reserved-word lists) in one spot.

Every identifier that goes into a ``psycopg2.sql.Identifier`` MUST come
through one of these checks first. ``sql.Identifier`` itself escapes
the value, but we still want to reject anything outside the allowed
charset before it gets near the SQL builder — defence in depth, plus
clearer error messages for clients.
"""

from __future__ import annotations

from api.ORM.sqlFunctions.utils.helpers import validate_identifier


class InvalidIdentifierError(ValueError):
    """Raised when a name fails identifier validation."""


def _validate(value: str, kind: str) -> str:
    try:
        return validate_identifier(value, kind)
    except Exception as exc:  # validate_identifier may raise ValueError
        raise InvalidIdentifierError(str(exc)) from exc


def validate_schema_name(schema: str) -> str:
    """Postgres schema name; rejected if not a strict SQL identifier."""
    return _validate(schema, "schema")


def validate_object_name(object_name: str) -> str:
    """Custom-object table name (== ``object.name`` in the registry)."""
    return _validate(object_name, "object_name")


def validate_field_name(field_name: str) -> str:
    """Custom-field column name."""
    return _validate(field_name, "field_name")
