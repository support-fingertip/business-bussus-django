"""
update_workflow.py  —  fixed version

BUG / SECURITY FIXES APPLIED
─────────────────────────────
[SEC-02] Schema was set INSIDE transaction.atomic() with SET LOCAL — which
         is correct. However the schema identifier was validated AFTER the
         cursor.execute call in some code paths, leaving a window for
         injection. Fixed: validate first, execute second, consistently.

[SEC-03] The original code validated `schema` and `trigger_type` with
         _validate_identifier but NOT `module_name` before embedding it in
         get_fields_metadata() calls. Any user-controlled module_name
         bypassed the guard. Fixed: validate module_name before any use.

[BUG-09] extra_fields was extracted twice from the same node dict (lines
         duplicated verbatim in the original). The second extraction
         overwrote the first — harmless here but a clear copy-paste bug
         removed.

[BUG-10] validate_formula() was called with 4 positional args:
         (formula, fields_metadata, field_name, fields_metadata.get(field_name))
         The current formula_validation.py signature only accepts 3.
         The 4th arg (parent_expected_type) is always None when fetched via
         .get() because fields_metadata values are datatype strings, not a
         nested dict — so it was meaningless anyway.
         Fixed: 3-arg call.

[BUG-11] get_fields_metadata() was called without schema inside the
         update loop. During an update the search_path may not yet be set
         (it is set inside the later transaction.atomic() block).
         Fixed: pass schema kwarg consistently.

[BUG-12] Node INSERT was missing `created_date` — the column almost
         certainly has NOT NULL / DEFAULT CURRENT_TIMESTAMP but relying on
         a DB default silently breaks if the column has no default.
         Added explicit CURRENT_TIMESTAMP.

[BUG-13] Node insertion errors were caught and silently continued
         (`except Exception: continue`). This means a partially-inserted
         node set could leave the workflow in a broken state while returning
         HTTP 200. Removed the bare except; errors now bubble up and the
         enclosing transaction.atomic() rolls back everything cleanly.

[BUG-14] Edge insertion: if source_node or target_node was not found the
         code used `continue` (silently skipped the edge). Workflow would
         save with missing connections. Changed to raise ValueError so the
         whole update is rolled back.

[LOGIC-03] The response did not include `last_modified_date` / timestamps
           even though the update query sets them. Added them (as ISO
           strings) for consistency with create_workflow response.

[LOGIC-04] Formula validation loop fetched fields_metadata once per field
           (same BUG-04 pattern as create_workflow). Fixed: cache per module.
"""

import json
import re
from datetime import datetime, timezone
from django.db import connection, transaction

from api.ORM.setup.workflows.create_workflow import get_fields_metadata
from api.formulas.formula_validation import validate_formula

# ── identifier safety ────────────────────────────────────────────────────────
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(value: str, field: str) -> str:
    if not value or not _IDENTIFIER_RE.fullmatch(str(value)):
        raise ValueError(f"Invalid identifier for {field}: '{value}'")
    return value


# ── main update function ──────────────────────────────────────────────────────
def update_workflow(request, update_data: dict, **kwargs) -> dict:
    try:
        workflow_data = update_data.get("workflow")
        if not workflow_data:
            raise ValueError("Missing 'workflow' data.")

        # ── Validate identifiers early ───────────────────────────────────────
        trigger_type = _validate_identifier(
            workflow_data["trigger_type"].lower().replace(" ", "_"), "trigger_type"
        )
        module_name = _validate_identifier(
            workflow_data.get("module_name"), "module_name"
        )
        schema = kwargs.get("schema")
        if not schema:
            raise ValueError("Schema is required.")
        _validate_identifier(schema, "schema")   # SEC-02: validate before any use

        workflow_id = workflow_data["id"]
        nodes_data = update_data.get("nodes", [])
        edges_data = update_data.get("edges", [])


        # ── Uniqueness check for workflow name (excluding current workflow) ──
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO %s, public", [schema])
            cursor.execute(
                "SELECT id FROM workflow WHERE name = %s AND id <> %s",
                [workflow_data["name"], workflow_id]
            )
            existing = cursor.fetchone()
        if existing:
            raise ValueError(f"Workflow name '{workflow_data['name']}' already exists. Please choose a unique name.")

        # ── Phase 1: formula validation (read-only, outside transaction) ─────
        _validate_formulas(nodes_data, trigger_type, module_name, schema)

        # ── Phase 2: DB writes ───────────────────────────────────────────────
        with transaction.atomic():
            with connection.cursor() as cursor:
                # SEC-02: schema already validated above
                cursor.execute("SET search_path TO %s, public", [schema])

            # 2a. Update workflow header
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE workflow
                    SET name = %s, description = %s, trigger_type = %s,
                        module_name = %s, last_modified_date = CURRENT_TIMESTAMP,
                        last_modified_by_id = %s
                    WHERE id = %s
                    """,
                    [
                        workflow_data["name"],
                        workflow_data.get("description", ""),
                        trigger_type,
                        module_name,
                        request.user.id,
                        workflow_id,
                    ],
                )

            # 2b. Delete existing edges first (FK constraint), then nodes
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM workflow_edge WHERE workflow_id = %s", [workflow_id]
                )
                cursor.execute(
                    "DELETE FROM workflow_node WHERE workflow_id = %s", [workflow_id]
                )

            # 2c. Insert new nodes
            dummy_id_to_node: dict = {}
            created_nodes: list = []

            for node_data in nodes_data:
                node_id_key = node_data.get("id")
                if not node_id_key:
                    raise ValueError("Node payload is missing 'id'.")

                data = node_data.get("data", {})
                node_type = data.get("type_name")
                if not node_type:
                    raise ValueError(
                        f"Node '{node_id_key}' is missing 'type_name'."
                    )

                # FIX BUG-13: removed bare except/continue — errors bubble up
                with connection.cursor() as cursor:
                    cursor.execute(
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
                            node_type,
                            json.dumps(node_data.get("position", {"x": 0, "y": 0})),
                            json.dumps(data),
                            json.dumps(node_data.get("measured", {})),
                            request.user.id,
                            request.user.id,
                        ],
                    )
                    node_id = cursor.fetchone()[0]

                dummy_id_to_node[node_id_key] = node_id
                created_nodes.append(node_id)

            if not dummy_id_to_node:
                raise ValueError(
                    "No nodes were inserted. Verify that nodes_data is not empty."
                )

            # 2d. Insert edges
            created_edges: list = []
            for edge_data in edges_data:
                source = edge_data.get("source") or edge_data.get("source_id")
                target = edge_data.get("target") or edge_data.get("target_id")

                if not source or not target:
                    raise ValueError(
                        f"Edge payload is missing 'source' or 'target': {edge_data}"
                    )

                source_node = dummy_id_to_node.get(source)
                target_node = dummy_id_to_node.get(target)

                # FIX BUG-14: raise instead of silently skipping
                if not source_node or not target_node:
                    missing = []
                    if not source_node:
                        missing.append(f"source '{source}'")
                    if not target_node:
                        missing.append(f"target '{target}'")
                    raise ValueError(
                        f"Edge references unknown node(s): {', '.join(missing)}. "
                        f"Available keys: {list(dummy_id_to_node.keys())}"
                    )

                with connection.cursor() as cursor:
                    cursor.execute(
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
                            request.user.id,
                            request.user.id,
                        ],
                    )
                    edge_id = cursor.fetchone()[0]

                created_edges.append({
                    "id": edge_id,
                    "source": source_node,
                    "target": target_node,
                    "source_handle": edge_data.get("sourceHandle"),
                })

        # ── Phase 3: build response ──────────────────────────────────────────
        now_iso = datetime.now(tz=timezone.utc).isoformat()  # LOGIC-03
        return {
            "message": "Workflow updated successfully.",
            "workflow": {
                "id": workflow_id,
                "name": workflow_data["name"],
                "description": workflow_data.get("description", ""),
                "trigger_type": trigger_type,
                "module_name": module_name,
                "last_modified_date": now_iso,
                "nodes": created_nodes,
                "edges": created_edges,
            },
        }

    except Exception as e:
        print(f"Error in update_workflow: {e}")
        raise Exception(f"Error occurred while updating workflow: {e}") from e


# ── formula validation helper ─────────────────────────────────────────────────
def _validate_formulas(nodes_data: list, trigger_type: str, module_name: str, schema) -> None:
    """
    Validate all formula fields across action nodes.

    FIX BUG-10: validate_formula called with 3 args.
    FIX BUG-11: schema passed to get_fields_metadata.
    FIX LOGIC-04: metadata fetched once per module, not once per field.
    FIX BUG-09: duplicate extra_fields extraction removed.
    """
    metadata_cache: dict = {}

    for node in nodes_data:
        if node.get("node_type") != "Action":
            continue

        filters = node.get("data", {}).get("filters", {})
        action_type = filters.get("actionType", "")

        if trigger_type == "delete_records" and action_type in ("update_field", "create_field"):
            raise ValueError("You can't Update or Create fields for a Delete trigger.")

        # FIX BUG-09: extracted once only
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

            # FIX LOGIC-04: cache metadata per module
            if module_name not in metadata_cache:
                # FIX BUG-11: pass schema
                metadata_cache[module_name] = get_fields_metadata(module_name, schema=schema)

            fields_metadata = metadata_cache[module_name]

            # FIX BUG-10: 3-arg call
            validate_formula(formula, fields_metadata, field_name)
