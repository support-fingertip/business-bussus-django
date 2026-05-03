"""Per-tenant metadata loader for dynamic-object tables.

Loads (and caches) the object/field metadata that drives every dynamic
SQL operation:
  - which custom objects exist in this tenant,
  - which physical columns each object has,
  - which datatypes / required flags / relationships each column carries.

Invalidation
------------
The cache is invalidated whenever the schema changes. Currently the
mutation entry points are:
  - ``api/ORM/setup/ObjectManager/post_object.py``
  - ``api/ORM/setup/ObjectManager/delete_object.py``
  - ``api/ORM/setup/ObjectManager/create_field.py``
  - ``api/ORM/setup/ObjectManager/delete_field.py``
  - ``api/ORM/setup/ObjectManager/field_execution.py``

Each of those should call ``invalidate_object`` /
``invalidate_schema`` after a successful change. Phase 2 wires those
calls in. For Phase 1 the cache is correct on first read and stale
after schema changes — acceptable for the scaffold since no callsite
yet relies on it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from django.core.cache import cache
from django.db import connection
from psycopg2 import sql

from api.ORM.dynamic.identifier_validator import (
    validate_object_name,
    validate_schema_name,
)

logger = logging.getLogger(__name__)

CACHE_VERSION = 1
DEFAULT_TTL_SECONDS = 300


def _object_cache_key(schema: str, object_name: str) -> str:
    return f"dynamic_obj:v{CACHE_VERSION}:{schema}:{object_name}"


def _schema_cache_key(schema: str) -> str:
    return f"dynamic_obj_list:v{CACHE_VERSION}:{schema}"


@dataclass(frozen=True)
class FieldMeta:
    name: str
    datatype: str
    required: bool
    is_modifiable: bool
    parent_object: Optional[str]
    relationship_name: Optional[str]


@dataclass(frozen=True)
class ObjectMeta:
    object_id: str
    name: str
    label: str
    setup: bool
    type_: str
    default_access_level: Optional[str]
    fields: tuple[FieldMeta, ...]

    def field_names(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields)

    def get_field(self, name: str) -> Optional[FieldMeta]:
        for f in self.fields:
            if f.name == name:
                return f
        return None


def load_object(schema: str, object_name: str) -> Optional[ObjectMeta]:
    """Return ObjectMeta for ``schema.object_name`` or None if not registered.

    Result is cached for ``DEFAULT_TTL_SECONDS``.
    """
    validate_schema_name(schema)
    validate_object_name(object_name)

    key = _object_cache_key(schema, object_name)
    cached = cache.get(key)
    if cached is not None:
        return cached

    with connection.cursor() as cur:
        cur.execute("SET search_path TO %s", [schema])
        cur.execute(
            "SELECT id, name, label, setup, type, default_access_level "
            "FROM object WHERE name = %s",
            [object_name],
        )
        row = cur.fetchone()
        if not row:
            cache.set(key, None, DEFAULT_TTL_SECONDS)
            return None
        object_id, name, label, setup_flag, type_, default_access_level = row

        cur.execute(
            "SELECT name, datatype, required, is_modifiable, "
            "       parent_object, relationship_name "
            "FROM fields WHERE object_id = %s "
            "ORDER BY name ASC",
            [object_id],
        )
        fields = tuple(
            FieldMeta(
                name=fname,
                datatype=datatype,
                required=bool(required),
                is_modifiable=bool(is_modifiable) if is_modifiable is not None else True,
                parent_object=parent_object,
                relationship_name=relationship_name,
            )
            for fname, datatype, required, is_modifiable, parent_object, relationship_name
            in cur.fetchall()
        )

    meta = ObjectMeta(
        object_id=str(object_id),
        name=name,
        label=label,
        setup=bool(setup_flag) if isinstance(setup_flag, bool)
              else str(setup_flag).lower() == "true",
        type_=type_ or "",
        default_access_level=default_access_level,
        fields=fields,
    )
    cache.set(key, meta, DEFAULT_TTL_SECONDS)
    return meta


def list_business_objects(schema: str) -> tuple[str, ...]:
    """All non-setup object names registered in this schema.

    Used by the dispatcher object-name whitelist (Phase 2).
    """
    validate_schema_name(schema)

    key = _schema_cache_key(schema)
    cached = cache.get(key)
    if cached is not None:
        return cached

    with connection.cursor() as cur:
        cur.execute("SET search_path TO %s", [schema])
        cur.execute(
            "SELECT name FROM object WHERE setup = FALSE ORDER BY name ASC"
        )
        names = tuple(r[0] for r in cur.fetchall())

    cache.set(key, names, DEFAULT_TTL_SECONDS)
    return names


def invalidate_object(schema: str, object_name: str) -> None:
    """Drop a single object's cache entry; call after metadata mutations."""
    cache.delete(_object_cache_key(schema, object_name))


def invalidate_schema(schema: str) -> None:
    """Drop the per-schema object list cache."""
    cache.delete(_schema_cache_key(schema))
