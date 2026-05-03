import logging
import re
from functools import lru_cache

from django.db import connection

logger = logging.getLogger("relationships")

# ---------------------------------------------------------------------------
# Identifier safety
# ---------------------------------------------------------------------------

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(value: str, kind: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"Invalid {kind} identifier: {value!r}")
    return value


def _validate_schema(schema: str) -> str:
    return _validate_identifier(schema, "schema")


def _set_search_path(cursor, schema: str) -> None:
    """
    BUG-1 FIX: Use SET search_path (session-scoped), not SET LOCAL
    (transaction-scoped). SET LOCAL silently does nothing outside a
    transaction block, causing queries to hit the wrong schema.

    BUG-2 FIX: Do NOT use %s parameterisation for the schema name.
    psycopg2 binds %s as a string literal ('schema'), not an identifier.
    After _validate_schema has confirmed the value matches [A-Za-z_][A-Za-z0-9_]*
    it is safe to interpolate directly.
    """
    cursor.execute(f"SET search_path TO {schema}")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_fields_metadata_for_object(object_name: str, schema: str) -> list[dict]:
    """Return all lookup_relationship field rows for *object_name*."""
    schema      = _validate_schema(schema)
    object_name = _validate_identifier(object_name, "object name")
    with connection.cursor() as cursor:
        _set_search_path(cursor, schema)          # BUG-1 + BUG-2 fixed
        cursor.execute(
            """
            SELECT name, datatype, relationship_name, parent_object
            FROM   fields
            WHERE  object_name = %s
              AND  datatype = 'lookup_relationship'
            """,
            [object_name],
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_child_fields_for_parent(parent_object: str, schema: str) -> list[dict]:
    """
    BUG-4 FIX: Instead of guessing child table names with candidate_names(),
    query the DB directly for all fields whose parent_object = *parent_object*.
    This is the correct way to find child relationships.
    Returns rows: {object_name, name, relationship_name, parent_object}
    """
    parent_object = _validate_identifier(parent_object, "parent object")
    schema        = _validate_schema(schema)
    with connection.cursor() as cursor:
        _set_search_path(cursor, schema)
        cursor.execute(
            """
            SELECT object_name, name, relationship_name, parent_object
            FROM   fields
            WHERE  parent_object = %s
              AND  datatype = 'lookup_relationship'
            """,
            [parent_object],
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# BUG-3 FIX: Module-level cache keyed on (schema, object_name).
# The original @lru_cache was defined INSIDE build_relationships_dynamic,
# so a brand-new empty cache was created on every request — zero benefit.
# Moving it here means the cache actually persists across requests.
# ---------------------------------------------------------------------------

@lru_cache(maxsize=512)
def _cached_fields_metadata(schema: str, object_name: str) -> tuple:
    return tuple(get_fields_metadata_for_object(object_name, schema))


@lru_cache(maxsize=512)
def _cached_child_fields(schema: str, parent_object: str) -> tuple:
    return tuple(get_child_fields_for_parent(parent_object, schema))


# ---------------------------------------------------------------------------
# build_relationships_dynamic
# ---------------------------------------------------------------------------

def build_relationships_dynamic(input_dict: dict, **kwargs) -> dict:
    root_table = _validate_identifier(input_dict.get("tableName", ""), "table name")
    schema     = _validate_schema(kwargs.get("schema", ""))
    relationships: dict = {}

    # ── Relationship name fuzzy matching ──────────────────────────────────────
    def candidate_names(name: str) -> list[str]:
        """
        BUG-11 FIX: Original code added BOTH a plural and a singular
        unconditionally, producing "accountss" from "accounts".
        Now: if name ends with 's' → also try without 's' (singular).
             if name does NOT end with 's' → also try with 's' (plural).
        Never add both directions at once.
        """
        if not name:
            return []
        base = name.lower()
        if base.endswith("s") and len(base) > 1:
            return [base, base[:-1]]        # "accounts" → ["accounts", "account"]
        return [base, base + "s"]           # "contact"  → ["contact", "contacts"]

    def relation_matches(actual: str, requested: str) -> bool:
        if not actual or not requested:
            return False
        actual_l    = actual.lower()
        requested_l = requested.lower()
        if actual_l == requested_l:
            return True
        return (
            requested_l in candidate_names(actual_l)
            or actual_l in candidate_names(requested_l)
        )

    # ── Field extraction ──────────────────────────────────────────────────────
    def extract_fields_recursively(obj) -> set:
        """
        BUG-10 FIX: Added "filters" and "where" to the handled keys.
        Filter entries commonly carry a "field" key with dotted paths
        that trigger relationship resolution.
        """
        fields_found: set = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("fields", "having"):
                    if isinstance(v, list):
                        for item in v:
                            if isinstance(item, str):
                                fields_found.add(item)
                            elif isinstance(item, dict):
                                if "name" in item and isinstance(item["name"], str):
                                    fields_found.add(item["name"])
                                if "field" in item and isinstance(item["field"], str):
                                    fields_found.add(item["field"])

                elif k == "order_by":
                    if isinstance(v, list):
                        for item in v:
                            if isinstance(item, dict) and "field" in item and isinstance(item["field"], str):
                                fields_found.add(item["field"])
                            elif isinstance(item, str):
                                fields_found.add(item)

                elif k == "group_by":
                    if isinstance(v, list):
                        for item in v:
                            if isinstance(item, str):
                                fields_found.add(item)
                            elif isinstance(item, dict) and "name" in item and isinstance(item["name"], str):
                                fields_found.add(item["name"])
                    elif isinstance(v, dict):
                        for item in v.get("rows", []) + v.get("columns", []):
                            if isinstance(item, str):
                                fields_found.add(item)
                            elif isinstance(item, dict) and "name" in item and isinstance(item["name"], str):
                                fields_found.add(item["name"])

                elif k in ("filters", "where"):
                    # BUG-10 FIX: filter clauses carry "field" references
                    if isinstance(v, list):
                        for item in v:
                            if isinstance(item, dict) and "field" in item and isinstance(item["field"], str):
                                fields_found.add(item["field"])
                    fields_found.update(extract_fields_recursively(v))

                elif k == "field" and isinstance(v, str):
                    fields_found.add(v)

                else:
                    fields_found.update(extract_fields_recursively(v))

        elif isinstance(obj, list):
            for item in obj:
                fields_found.update(extract_fields_recursively(item))

        return fields_found

    # ── Relationship resolution ───────────────────────────────────────────────
    def find_relationship_field(object_name: str, relationship_name: str) -> dict | None:
        """
        BUG-4 FIX: Child-direction lookup no longer guesses table names.
        It queries the DB for all fields whose parent_object == object_name,
        then matches relationship_name against the child's relationship_name.
        """
        # --- Parent: object_name has a FK pointing TO relationship_name -------
        for f in _cached_fields_metadata(schema, object_name):
            if (f.get("datatype") == "lookup_relationship" and
                    relation_matches(f.get("relationship_name", ""), relationship_name)):
                return {
                    "key":       f.get("name"),
                    "table":     f.get("parent_object"),
                    "direction": "parent",
                }

        # --- Child: some table has a FK pointing TO object_name ---------------
        # BUG-4 FIX: query DB for real child rows instead of guessing names
        for f in _cached_child_fields(schema, object_name):
            if relation_matches(f.get("relationship_name", ""), relationship_name):
                return {
                    "key":       f.get("name"),
                    "table":     f.get("object_name"),   # the child table
                    "direction": "child",
                }

        return None

    # ── Chain builder ─────────────────────────────────────────────────────────
    seen_chain_nodes: set = set()

    def build_relationship_chain(
        current_table: str,
        current_rel_path: str | None,
        path_steps: list[str],
    ) -> None:
        if not path_steps:
            return

        next_rel  = path_steps[0]
        node_key  = (current_table, current_rel_path or "", tuple(path_steps))
        if node_key in seen_chain_nodes:
            return
        seen_chain_nodes.add(node_key)

        rel_field = find_relationship_field(current_table, next_rel)
        if rel_field:
            # BUG-5 FIX: build the full path, not just the last segment.
            # Original code used only the last part of current_rel_path,
            # so "leads.accounts.contacts" was built as "accounts.contacts"
            # — losing the leading "leads." and causing key collisions.
            if current_rel_path is None:
                new_rel_path = f"{current_table}.{next_rel}"
            else:
                new_rel_path = f"{current_rel_path}.{next_rel}"   # full chain

            if new_rel_path not in relationships:
                relationships[new_rel_path] = rel_field

            build_relationship_chain(rel_field["table"], new_rel_path, path_steps[1:])

    # ── Main loop ─────────────────────────────────────────────────────────────
    all_fields      = extract_fields_recursively(input_dict)
    processed_steps: set = set()

    for field_path in all_fields:
        if not isinstance(field_path, str):
            continue
        parts              = field_path.split(".")
        relationship_steps = parts[:-1]
        if relationship_steps:
            steps_key = tuple(relationship_steps)
            if steps_key in processed_steps:
                continue
            processed_steps.add(steps_key)
            build_relationship_chain(root_table, None, relationship_steps)

    input_dict["relationships"] = relationships
    return input_dict


# ---------------------------------------------------------------------------
# Reporting relationships
# ---------------------------------------------------------------------------

def get_lookup_relationships(table: str, **kwargs) -> list[dict]:
    table  = _validate_identifier(table, "table")
    schema = _validate_schema(kwargs.get("schema", ""))
    with connection.cursor() as cursor:
        _set_search_path(cursor, schema)          # BUG-1 + BUG-2 fixed
        cursor.execute(
            """
            SELECT object_name, name, relationship_name, parent_object
            FROM   fields
            WHERE  datatype = 'lookup_relationship'
              AND  (object_name = %s OR parent_object = %s)
            """,
            [table, table],
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def find_relationship_paths(
    table: str,
    direction: str,
    level: int = 0,
    max_depth: int = 3,
    visited: set | None = None,
    path: list | None = None,
    **kwargs,
) -> list[list[str]]:
    """
    BUG-6 FIX: Pass *visited* by reference (shared mutable set), not as a
    copy. Original code used visited.copy() for every recursive call, so
    each sibling branch had its own isolated visited set. This meant the
    same table could be visited multiple times across branches, causing
    duplicate paths and potential runaway recursion on circular schemas.

    With a shared visited set, once a table is entered in any branch it
    won't be entered again — the max_depth guard stops remaining depth.
    """
    if direction not in {"parent", "child"}:
        raise ValueError("direction must be 'parent' or 'child'")
    if max_depth < 1:
        return []
    if visited is None:
        visited = set()
    if path is None:
        path = [table]
    if level >= max_depth or table in visited:
        return []

    visited.add(table)
    relationships_list = get_lookup_relationships(table, **kwargs)

    # BUG-7 FIX: removed pprint(relationships) debug print
    logger.debug("[relationships] table=%s direction=%s level=%d rels=%d",
                 table, direction, level, len(relationships_list))

    result = []
    for rel in relationships_list:
        if direction == "parent" and rel["object_name"] == table:
            parent = rel["parent_object"]
            if parent and parent not in visited:
                new_path = path + [parent]
                result.append(new_path)
                result.extend(
                    find_relationship_paths(
                        parent, direction,
                        level + 1, max_depth,
                        visited,        # BUG-6 FIX: shared set, not .copy()
                        new_path,
                        **kwargs,
                    )
                )

        elif direction == "child" and rel["parent_object"] == table:
            child = rel["object_name"]
            if child and child not in visited:
                new_path = path + [child]
                result.append(new_path)
                result.extend(
                    find_relationship_paths(
                        child, direction,
                        level + 1, max_depth,
                        visited,        # BUG-6 FIX: shared set, not .copy()
                        new_path,
                        **kwargs,
                    )
                )

    return result


def get_object_types(**kwargs) -> dict:
    schema = _validate_schema(kwargs.get("schema", ""))
    with connection.cursor() as cursor:
        _set_search_path(cursor, schema)          # BUG-1 + BUG-2 fixed
        cursor.execute("SELECT name, type FROM object")
        return dict(cursor.fetchall())


def get_object_relationships(table: str, **kwargs) -> dict:
    """
    BUG-8 FIX: children and child_paths were hardcoded as empty lists.
    find_relationship_paths is now called for both directions so the
    response is complete.
    """
    table = _validate_identifier(table, "table")

    parent_paths = find_relationship_paths(table, direction="parent", **kwargs)
    child_paths  = find_relationship_paths(table, direction="child",  **kwargs)   # BUG-8 FIX

    # Deduplicate paths
    def dedup(paths: list[list]) -> list[list]:
        seen: set = set()
        out: list = []
        for p in paths:
            key = tuple(p)
            if key not in seen:
                seen.add(key)
                out.append(p)
        return out

    filtered_parent_paths = dedup(parent_paths)
    filtered_child_paths  = dedup(child_paths)

    unique_parents  = list({p[-1] for p in filtered_parent_paths})
    unique_children = list({p[-1] for p in filtered_child_paths})   # BUG-8 FIX

    # Collect all involved object names for type lookup
    all_objects = {table}
    for path in filtered_parent_paths + filtered_child_paths:
        all_objects.update(path)

    object_types = get_object_types(**kwargs)
    types = {obj: object_types.get(obj, "unknown") for obj in all_objects}

    return {
        "success": True,
        "data": {
            "object":       table,
            "parents":      unique_parents,
            "children":     unique_children,          # BUG-8 FIX
            "parent_paths": filtered_parent_paths,
            "child_paths":  filtered_child_paths,     # BUG-8 FIX
            "types":        types,
        },
    }