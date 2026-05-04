"""
create_workflow.py  —  fixed version

BUG / SECURITY FIXES APPLIED
─────────────────────────────
[SEC-01] execute_sql() used f-string interpolation for the schema name
         ("SET search_path TO {schema}") — direct SQL injection vector.
         Fixed: validate schema with _IDENTIFIER_RE before use; keep the
         parameterised form for the actual SET statement.

[BUG-01] workflow_data guard ("if not workflow_data") was placed AFTER
         workflow_data was already accessed (trigger_type line), so the
         guard could never fire — it raised KeyError first.
         Fixed: moved the guard to the top of the try block.

[BUG-02] validate_formula() in formula_validation.py accepts 3 positional
         args (formula, fields_metadata, field_name).  create_workflow.py
         was passing a 4th positional arg (fields_metadata.get('field_name'))
         which is always None and caused a TypeError because the current
         signature does not accept it.
         Fixed: call with 3 args only.

[BUG-03] validate_single_formula() used `object` as a variable name,
         shadowing the Python built-in.  Renamed to `module_name`.

[BUG-04] get_fields_metadata() was called inside the formula-validation
         loop (once per field) — potentially dozens of DB round-trips for a
         single node.  Fixed: fetch once per node and reuse.

[BUG-05] response_data used request.user.id (Django ORM attribute) while
         the rest of the function used user.get('id') (dict).  This would
         raise AttributeError if user is a plain dict (as implied by the
         kwargs pattern).  Fixed to use user.get('id') consistently.

[BUG-06] response_data set "created_date" / "last_modified_date" to the
         literal string "CURRENT_TIMESTAMP" instead of an actual timestamp.
         Fixed: use datetime.utcnow().isoformat().

[BUG-07] parse_functions() in formula_validation split by top-level commas
         which breaks for any multi-param function — the outer formula
         "ADDDAY(created_date, 5)" was split into ["ADDDAY(created_date",
         "5)"], both of which are invalid function strings.
         Fixed in formula_validation.py (see that file).

[BUG-08] Node INSERT is missing created_date column but the table DDL
         almost certainly has NOT NULL on it. update_workflow.py had the
         same omission.  Added CURRENT_TIMESTAMP for created_date.

[LOGIC-01] Formula validation was done OUTSIDE the transaction.atomic()
           block, but the workflow and nodes were created INSIDE it.  If
           validation passed but the INSERT failed, there was no problem;
           but if the INSERT succeeded and a later step failed, the
           validation work was wasted and the error message was confusing.
           More importantly, get_fields_metadata() inside the loop could
           race with concurrent schema changes.  Validation now stays
           outside the transaction (correct — read-only) but is clearly
           separated.

[LOGIC-02] edge_data['source'] / edge_data['target'] were accessed without
           .get() — KeyError if the frontend omits them.  Fixed to use .get()
           with an explicit error.
"""

import json
import re
from datetime import datetime, timezone
from django.db import connection, transaction

from api.formulas.formula_validation import validate_formula
from api.security.schema_authority import get_validated_schema

# ── identifier safety ────────────────────────────────────────────────────────
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(value: str, field: str) -> str:
    """Raise ValueError if value is not a safe SQL identifier."""
    if not value or not _IDENTIFIER_RE.fullmatch(str(value)):
        raise ValueError(f"Invalid identifier for {field}: '{value}'")
    return value


# ── low-level SQL helper ──────────────────────────────────────────────────────
def execute_sql(query, params=None, schema=None, fetchone=False, fetchall=False, returning=False):
    """
    Execute SQL with optional schema scoping.

    FIX SEC-01: schema is validated with _IDENTIFIER_RE before being
    interpolated — it must be a bare identifier (no quotes, no semicolons).
    The SET statement still uses a parameterised placeholder so psycopg2
    handles quoting.
    """
    with connection.cursor() as cursor:
        if schema:
            _validate_identifier(schema, "schema")          # SEC-01
            cursor.execute("SET search_path TO %s, public", [schema])
        cursor.execute(query, params or [])
        if returning:
            return cursor.fetchone()[0]
        if fetchone:
            return cursor.fetchone()
        if fetchall:
            return cursor.fetchall()


# ── metadata helper ───────────────────────────────────────────────────────────
def get_fields_metadata(object_name: str, schema=None) -> dict:
    """Return {field_name: datatype} for the given object."""
    query = "SELECT name, datatype FROM fields WHERE object_name = %s"
    rows = execute_sql(query, [object_name], schema=schema, fetchall=True)
    return {name: datatype for name, datatype in (rows or [])}


# ── main create function ──────────────────────────────────────────────────────
def create_workflow(request, create_data: dict, **kwargs) -> dict:
    user = kwargs.get("user_")
    schema = get_validated_schema(kwargs)

    try:
        workflow_data = create_data.get("workflow")
        # FIX BUG-01: guard before any access
        if not workflow_data:
            raise ValueError("Missing 'workflow' data.")

        trigger_type = workflow_data["trigger_type"].lower().replace(" ", "_")
        nodes_data = create_data.get("nodes", [])
        edges_data = create_data.get("edges", [])


        # ── Uniqueness check for workflow name ──────────────────────────────
        existing = execute_sql(
            "SELECT id FROM workflow WHERE name = %s",
            [workflow_data["name"]],
            schema=schema,
            fetchone=True,
        )
        if existing:
            raise ValueError("Please select unique name")

        # ── Phase 1: formula validation (outside transaction — read-only) ────
        _validate_formulas(nodes_data, trigger_type, workflow_data.get("module_name"), schema)

        # ── Phase 2: DB writes inside a single transaction ───────────────────
        with transaction.atomic():
            # FIX SEC-01: set schema inside atomic so it is rolled back on failure
            if schema:
                _validate_identifier(schema, "schema")
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL search_path TO %s, public", [schema])

            # 2a. Insert workflow
            workflow_id = execute_sql(
                """
                INSERT INTO workflow
                    (name, description, trigger_type, module_name,
                     created_date, last_modified_date, created_by_id, last_modified_by_id)
                VALUES (%s, %s, %s, %s,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, %s, %s)
                RETURNING id
                """,
                [
                    workflow_data["name"],
                    workflow_data.get("description", ""),
                    trigger_type,
                    workflow_data.get("module_name"),
                    user.get("id"),
                    user.get("id"),
                ],
                returning=True,
            )

            # 2b. Insert nodes
            dummy_id_to_node: dict = {}
            created_nodes: list = []

            for node_data in nodes_data:
                data = node_data.get("data", {})
                node_id = execute_sql(
                    """
                    INSERT INTO workflow_node
                        (workflow_id, label, type, node_type, position, data, measured,
                         created_date, last_modified_date, created_by_id, last_modified_by_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s,
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, %s, %s)
                    RETURNING id
                    """,
                    [
                        workflow_id,
                        data.get("label"),
                        node_data.get("type", "standard"),
                        data.get("type_name"),
                        json.dumps(node_data.get("position", {"x": 0, "y": 0})),
                        json.dumps(data),
                        json.dumps(node_data.get("measured", {})),
                        user.get("id"),
                        user.get("id"),
                    ],
                    returning=True,
                )
                dummy_id_to_node[node_data["id"]] = node_id
                created_nodes.append(node_id)

            # 2c. Insert edges
            created_edges: list = []
            for edge_data in edges_data:
                # FIX LOGIC-02: use .get() to avoid KeyError
                source = edge_data.get("source")
                target = edge_data.get("target")
                if not source or not target:
                    raise ValueError(
                        f"Edge is missing 'source' or 'target': {edge_data}"
                    )

                source_node = dummy_id_to_node.get(source)
                target_node = dummy_id_to_node.get(target)
                if not source_node or not target_node:
                    raise ValueError(
                        f"Edge references unknown node IDs: source={source}, target={target}"
                    )

                edge_id = execute_sql(
                    """
                    INSERT INTO workflow_edge
                        (workflow_id, source_id, target_id, source_handle,
                         created_date, last_modified_date, created_by_id, last_modified_by_id)
                    VALUES (%s, %s, %s, %s,
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, %s, %s)
                    RETURNING id
                    """,
                    [
                        workflow_id,
                        source_node,
                        target_node,
                        edge_data.get("sourceHandle"),
                        user.get("id"),
                        user.get("id"),
                    ],
                    returning=True,
                )
                created_edges.append({
                    "id": edge_id,
                    "source": source_node,
                    "target": target_node,
                    "source_handle": edge_data.get("sourceHandle"),
                })

        # ── Phase 3: build response ──────────────────────────────────────────
        now_iso = datetime.now(tz=timezone.utc).isoformat()  # FIX BUG-06
        return {
            "message": "Workflow created successfully",
            "workflow": {
                "id": workflow_id,
                "name": workflow_data["name"],
                "description": workflow_data.get("description", ""),
                "trigger_type": trigger_type,
                "module_name": workflow_data.get("module_name"),
                "created_date": now_iso,
                "last_modified_date": now_iso,
                "created_by_id": user.get("id"),       # FIX BUG-05
                "last_modified_by_id": user.get("id"), # FIX BUG-05
                "nodes": created_nodes,
                "edges": created_edges,
            },
        }

    except Exception as e:
        print(f"Error in create_workflow: {e}")
        raise Exception(str(e)) from e


# ── formula validation helper ─────────────────────────────────────────────────
def _validate_formulas(nodes_data: list, trigger_type: str, module_name: str, schema) -> None:
    """
    Validate all formula fields across all action nodes.

    FIX BUG-04: fields_metadata is fetched ONCE per module (cached in a
    local dict) instead of once per field.
    FIX BUG-02: validate_formula called with 3 args (not 4).
    """
    metadata_cache: dict = {}

    for node in nodes_data:
        if node.get("node_type") != "Action":
            continue

        filters = node.get("data", {}).get("filters", {})
        action_type = filters.get("actionType", "")

        if trigger_type == "delete_records" and action_type in ("update_field", "create_field"):
            raise ValueError("You can't Update or Create fields for a Delete trigger.")

        extra_fields = filters.get("config", {}).get("extraFields", [])
        for field_info in extra_fields:
            if field_info.get("valueType") != "formula":
                continue

            field_name = field_info.get("name")
            formula = field_info.get("value")

            if not formula or not isinstance(formula, str):
                raise ValueError(
                    f"Invalid formula configuration for field '{field_name}' "
                    f"in node '{node.get('id')}'"
                )

            # FIX BUG-04: fetch once, reuse
            if module_name not in metadata_cache:
                metadata_cache[module_name] = get_fields_metadata(module_name, schema=schema)

            fields_metadata = metadata_cache[module_name]

            # FIX BUG-02: 3-arg call — signature is (formula, fields_metadata, field_name)
            validate_formula(formula, fields_metadata, field_name)


# ── standalone formula validator (API endpoint helper) ────────────────────────
def validate_single_formula(**kwargs) -> bool:
    """
    Validate a single formula string for a given module + field.

    FIX BUG-03: renamed `object` variable to `module_name`.
    FIX BUG-02: validate_formula called with 3 args.
    """
    module_name = kwargs.get("module_name")   # FIX BUG-03: was `object`
    field_name  = kwargs.get("field_name")
    formula     = kwargs.get("formula")
    schema      = get_validated_schema(kwargs)

    if not formula or formula in ("", "null"):
        raise ValueError("Empty or invalid formula.")

    fields_metadata = get_fields_metadata(module_name, schema=schema)
    # FIX BUG-02: 3-arg call
    return validate_formula(formula, fields_metadata, field_name)
