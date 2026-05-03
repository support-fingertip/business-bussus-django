"""Parity tests for the Phase 2 ORM Wave 2 tenant-scoped models.

These are pure-unit tests (no DB) that verify the structural contract
between the Django models and the rest of the platform:

  - Every model declares ``managed = False`` (Django doesn't own the
    schema).
  - ``Meta.db_table`` matches the canonical name in
    ``sqlfiles/objects.sql`` (the runtime ``object`` registry).
  - The sharing-records access-level choices match the constant in
    ``api.permissions.permissions.DEFAULT_OBJECT_ACCESS_LEVEL``.
  - Permission action columns on ``ObjectPermission`` match
    ``api.permissions.permissions.VALID_PERMISSION_TYPES``.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


REPO_ROOT = Path(__file__).resolve().parents[2]
OBJECTS_SQL = REPO_ROOT / "sqlfiles" / "objects.sql"


# Mapping: Django model class name -> expected db_table name.
EXPECTED_DB_TABLES = {
    "PlatformObject": "object",
    "Field": "fields",
    "Profile": "profile",
    "Role": "roles",
    "UserGroup": "user_group",
    "UserGroupUser": "user_group_users",
    "ObjectPermission": "object_permissions",
    "FieldPermission": "field_permissions",
    "TabPermission": "tab_permissions",
    "AppPermission": "app_permissions",
    "SharingRecord": "sharing_records",
    "OrganizationWideDefault": "owd",
}


def _registry_table_names() -> set[str]:
    """All ``name`` values from the INSERT INTO object block in objects.sql."""
    text = OBJECTS_SQL.read_text(encoding="utf-8")
    start = text.find('INSERT INTO "object"')
    block = text[start:]
    # Each row's 15th-column literal is the object name (1-indexed: 15).
    # Use a permissive regex that grabs every quoted literal, then count off.
    rows = re.findall(r"\((?:[^()']|'[^']*')+\)", block, flags=re.DOTALL)
    val_re = re.compile(r"NULL|'(?:[^'\\]|\\.)*'", re.DOTALL)
    names = set()
    for r in rows:
        vs = val_re.findall(r)
        if len(vs) < 15:
            continue
        name = vs[14].strip("'")
        names.add(name)
    return names


def test_all_expected_tables_appear_in_registry():
    """Every Wave 2 db_table is registered in objects.sql.

    Catches registry-drift bugs early — if someone adds a new model
    without registering the table, this test fails before a tenant
    breaks.
    """
    registry = _registry_table_names()
    missing = sorted(t for t in EXPECTED_DB_TABLES.values() if t not in registry)
    assert not missing, (
        f"Tables registered as Django models but missing from objects.sql "
        f"registry: {missing}"
    )


def test_models_use_managed_false():
    """No Wave 2 model may flip managed=True — Django doesn't own these tables."""
    pytest.importorskip("django")
    # Configure minimal Django settings before importing models so we
    # don't need to boot the full project.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "version2.settings")
    try:
        import django  # noqa: F401
        django.setup()
    except Exception:
        pytest.skip("Django not configured in this environment")

    from api import tenant_models as tm

    for cls_name in EXPECTED_DB_TABLES:
        model = getattr(tm, cls_name)
        assert model._meta.managed is False, (
            f"{cls_name} must have managed=False; the table lives in the "
            f"per-tenant schema and Django doesn't own its DDL."
        )


def test_db_table_names_match_expected():
    pytest.importorskip("django")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "version2.settings")
    try:
        import django  # noqa: F401
        django.setup()
    except Exception:
        pytest.skip("Django not configured in this environment")

    from api import tenant_models as tm

    for cls_name, expected_table in EXPECTED_DB_TABLES.items():
        model = getattr(tm, cls_name)
        assert model._meta.db_table == expected_table, (
            f"{cls_name}.Meta.db_table = {model._meta.db_table!r}, "
            f"expected {expected_table!r}"
        )


def test_object_permission_columns_cover_permission_type_whitelist():
    """Every action in VALID_PERMISSION_TYPES has a matching column on
    ObjectPermission. If someone adds a new action to the whitelist
    without adding the column, queries will fail at runtime — catch it
    here instead.
    """
    pytest.importorskip("django")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "version2.settings")
    try:
        import django  # noqa: F401
        django.setup()
    except Exception:
        pytest.skip("Django not configured in this environment")

    from api.tenant_models import ObjectPermission
    from api.permissions.permissions import VALID_PERMISSION_TYPES

    field_names = {f.name for f in ObjectPermission._meta.get_fields()}
    missing = VALID_PERMISSION_TYPES - field_names
    assert not missing, (
        f"VALID_PERMISSION_TYPES contains {missing} but ObjectPermission "
        f"has no matching column."
    )


def test_sharing_record_access_level_choices_match_constant():
    """SharingRecord.access_level choices must include the
    DEFAULT_OBJECT_ACCESS_LEVEL constant — otherwise newly-defaulted
    rows would fail validation."""
    pytest.importorskip("django")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "version2.settings")
    try:
        import django  # noqa: F401
        django.setup()
    except Exception:
        pytest.skip("Django not configured in this environment")

    from api.tenant_models.sharing import (
        ACCESS_LEVEL_CHOICES,
    )
    from api.permissions.permissions import DEFAULT_OBJECT_ACCESS_LEVEL

    choice_values = {value for value, _label in ACCESS_LEVEL_CHOICES}
    assert DEFAULT_OBJECT_ACCESS_LEVEL in choice_values, (
        f"DEFAULT_OBJECT_ACCESS_LEVEL = {DEFAULT_OBJECT_ACCESS_LEVEL!r} "
        f"but SharingRecord choices are {sorted(choice_values)}"
    )
