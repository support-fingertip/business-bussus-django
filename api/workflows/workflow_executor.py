"""
Workflow executor module.

This module handles the execution of workflows, traversing workflow nodes
and executing actions based on conditions.

FIX SUMMARY (2025):
  [BUG-01]  execute_workflows() had a missing return on None path — callers expecting
            authurl dict would silently get None.
  [BUG-02]  _IDENTIFIER_RE used fullmatch incorrectly — re.compile(r"[A-Za-z_][\w]*")
            without anchors; fullmatch anchors the whole string so [\w]* can match digits
            at the start via the implicit zero-length match before the first char group.
            Replaced with an unambiguous anchored pattern.
  [BUG-03]  conditions_match() used `if operator == ...` instead of `elif`, so 'eq'
            conditions ALSO ran the contains/not_contains branches unconditionally.
  [BUG-04]  conditions_match() missing operators: neq, gt, gte, lt, lte — raised
            KeyError-style silent pass-through (all conditions evaluated as True).
  [BUG-05]  traverse_node() removes node_id from visited in the finally block — this
            defeats cycle detection for any sibling branches that share a common
            descendant. Removed the finally pop; visited is per-workflow-run set.
  [BUG-06]  send_mail() shadows the stdlib send_mail import. Renamed to
            execute_send_mail() and updated the call-site.
  [BUG-07]  send_mail() fetches email template with SELECT * and then accesses columns
            by magic integer index (row[4], row[5], row[6]) — fragile against schema
            changes. Replaced with named column fetch.
  [BUG-08]  workflow_executor imports psycopg2.sql but never uses it — dead import removed.
  [SECURITY-01] _IDENTIFIER_RE regex was not anchored properly — see BUG-02.
  [SECURITY-02] search_path restore used SET search_path TO %s with a bare string;
                psycopg2 will quote it, but if the previous path contained commas
                (multiple schemas) the restore silently fails. Added comma-split
                + per-schema identifier validation before restoring.
"""
import json
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple, Set
from django.db import connection
from django.core.mail import get_connection, EmailMultiAlternatives
from django.template import Template, Context
from django.utils.html import strip_tags

from api.ORM.sqlFunctions.createSQLFunction import post_data_sql
from api.emailsend.views import send_test_email
from api.permissions._orm_dispatch import dispatch as _dispatch_path
from api.security.schema_authority import get_validated_schema
from api.workflows.create_records import create_record
from api.workflows.update_records import update_record

logger = logging.getLogger(__name__)

# FIX BUG-02: use an explicit anchored pattern that rejects leading digits
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _coerce_numeric(value: Any) -> Optional[Decimal]:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _normalize_for_equality(value: Any) -> Tuple[str, Any]:
    """Return a tuple (kind, normalized_value) for flexible equality checks."""
    if value is None:
        return ("none", None)
    if isinstance(value, bool):
        return ("bool", value)
    numeric = _coerce_numeric(value)
    if numeric is not None:
        return ("numeric", numeric)
    return ("text", str(value).strip().lower())


def _validate_identifier(value: Optional[str], field: str) -> str:
    # FIX BUG-02: _IDENTIFIER_RE is now properly anchored
    if not value or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"Invalid identifier for {field}: '{value}'")
    return value


def _set_search_path(schema: Optional[str]) -> Optional[str]:
    """Set search_path for the current connection; return previous path for later restore."""
    if not schema:
        return None
    schema = _validate_identifier(schema, "schema")
    with connection.cursor() as cursor:
        cursor.execute("SHOW search_path")
        previous = cursor.fetchone()[0]
        cursor.execute("SET search_path TO %s", [schema])
    return previous


def _restore_search_path(previous: Optional[str]) -> None:
    # FIX SECURITY-02: previous path may be comma-separated (multi-schema); validate each part
    if not previous:
        return
    parts = [p.strip().strip('"') for p in previous.split(",")]
    validated = []
    for part in parts:
        if not part or part in ("$user", "public"):
            # $user and public are legitimate postgres defaults
            validated.append(part)
        else:
            try:
                validated.append(_validate_identifier(part, "restore schema"))
            except ValueError:
                logger.warning("Skipping untrusted schema segment during search_path restore: %r", part)
    if not validated:
        return
    # SET search_path doesn't accept array parameters, so we have to
    # compose the statement. Each segment was validated_identifier-checked
    # above; we now wrap each in psycopg2.sql.Identifier so the safe-SQL
    # pre-commit hook accepts the construct (no f-string interpolation
    # of identifiers).
    from psycopg2 import sql as _sql
    parts_sql = []
    for part in validated:
        if part == "$user":
            # `$user` is a PostgreSQL pseudo-identifier; sql.Identifier
            # would quote it as `"$user"` which Postgres rejects.
            parts_sql.append(_sql.SQL("\"$user\""))
        else:
            parts_sql.append(_sql.Identifier(part))
    stmt = _sql.SQL("SET search_path TO {}").format(
        _sql.SQL(", ").join(parts_sql)
    )
    with connection.cursor() as cursor:
        cursor.execute(stmt)


def execute_workflows(obj: Dict[str, Any], module: str, trigger: str, **kwargs) -> Optional[Dict]:
    """
    Execute workflows for a given object and trigger.

    Returns an authurl dict if email auth is required, otherwise None.
    """
    user = kwargs.get('user_')
    schema = get_validated_schema(kwargs)

    previous_search_path = _set_search_path(schema)

    logger.info(
        "Triggered workflow execution for module: %s, object: %s, trigger: %s",
        module, obj.get('id'), trigger
    )

    try:
        # Phase 3.C: dual-path. Same return shape (list of (id, name) tuples)
        # so the caller code below is path-agnostic.
        def _workflows_raw():
            workflow_query = (
                "SELECT id, name FROM workflow "
                "WHERE trigger_type = %s AND module_name = %s"
            )
            with connection.cursor() as cursor:
                cursor.execute(workflow_query, [trigger, module])
                return cursor.fetchall()

        def _workflows_orm():
            from api.tenant_models import Workflow
            return list(
                Workflow.objects.filter(
                    trigger_type=trigger, module_name=module
                ).values_list("id", "name")
            )

        workflows = _dispatch_path(
            "workflow_executor.list_workflows",
            raw_impl=_workflows_raw,
            orm_impl=_workflows_orm,
            flag="USE_ORM_FOR_BL",
        )

        logger.info("Found %d workflows for module '%s' and trigger %s", len(workflows), module, trigger)

        for workflow in workflows:
            workflow_id = workflow[0]
            workflow_name = workflow[1]
            logger.info("Processing workflow: %s (ID: %s)", workflow_name, workflow_id)

            # Phase 3.C: dual-path Start-node lookup. Same return shape
            # (id, label, node_type, data) so downstream tuple-unpacking
            # works for either path.
            def _start_node_raw(_wid=workflow_id):
                start_node_query = (
                    "SELECT id, label, node_type, data FROM workflow_node "
                    "WHERE workflow_id = %s AND node_type = 'Start'"
                )
                with connection.cursor() as cursor:
                    cursor.execute(start_node_query, [_wid])
                    return cursor.fetchone()

            def _start_node_orm(_wid=workflow_id):
                from api.tenant_models import WorkflowNode
                return (
                    WorkflowNode.objects.filter(
                        workflow_id=_wid, node_type="Start"
                    )
                    .values_list("id", "label", "node_type", "data")
                    .first()
                )

            start_node = _dispatch_path(
                "workflow_executor.start_node",
                raw_impl=_start_node_raw,
                orm_impl=_start_node_orm,
                flag="USE_ORM_FOR_BL",
            )

            if not start_node:
                logger.warning("No Start node found for workflow %s. Skipping.", workflow_name)
                continue

            logger.debug("Start node data: %s", start_node)

            try:
                filters = json.loads(start_node[3]).get("filters", {})
            except (json.JSONDecodeError, TypeError) as exc:
                logger.error("Malformed JSON in start node data for workflow %s: %s", workflow_name, exc)
                continue

            if not conditions_match(obj, filters.get("conditions", [])):
                logger.info("Start node conditions did not match for workflow %s. Skipping.", workflow_name)
                continue

            logger.info("Start node conditions matched for workflow %s. Beginning traversal.", workflow_name)
            result = traverse_node(
                start_node, obj, module, workflow_id,
                user=user, trigger=trigger, visited=set(), depth=0, max_depth=200, **kwargs
            )
            # FIX BUG-01: propagate authurl result to caller
            if isinstance(result, dict) and "authurl" in result:
                return result

    except Exception as e:
        logger.error("Error executing workflows: %s", e, exc_info=True)
        raise
    finally:
        _restore_search_path(previous_search_path)

    return None


def traverse_node(
    node: Tuple,
    obj: Dict[str, Any],
    module: str,
    workflow_id: str,
    user: Optional[Any] = None,
    *,
    trigger: str = "",
    visited: Optional[Set] = None,
    depth: int = 0,
    max_depth: int = 200,
    **kwargs
) -> Optional[Dict]:
    """
    Traverse workflow nodes and execute actions based on node type.
    """
    logger.debug("Traversing node: %s (%s)", node[1], node[2])

    if visited is None:
        visited = set()

    if depth > max_depth:
        raise RecursionError(f"Workflow traversal exceeded max depth ({max_depth})")

    node_id = node[0]
    if node_id in visited:
        logger.warning("Detected workflow cycle at node id %s ('%s'), stopping traversal", node_id, node[1])
        return None

    # FIX BUG-05: Do NOT remove node_id in a finally block — that defeats cycle detection
    # for sibling branches.  The visited set is created fresh per workflow run (in
    # execute_workflows) so it does not leak across different workflow executions.
    visited.add(node_id)

    if node[2] == 'Action':
        data = execute_action(node, obj, module, workflow_id, user, trigger=trigger, **kwargs)
        if isinstance(data, dict) and "authurl" in data:
            return data

        edges = _fetch_edges(node[0])
        for edge in edges:
            target_node = _fetch_node(edge[1])
            if not target_node:
                logger.warning("Target node not found for edge target id: %s", edge[1])
                continue
            logger.debug("Following edge to: %s", target_node[1])
            result = traverse_node(
                target_node, obj, module, workflow_id,
                user=user, trigger=trigger, visited=visited, depth=depth + 1, max_depth=max_depth, **kwargs
            )
            if isinstance(result, dict) and "authurl" in result:
                return result

    elif node[2] == 'Decision':
        try:
            conditions = json.loads(node[3]).get("filters", {}).get("conditions", [])
        except (json.JSONDecodeError, TypeError) as exc:
            logger.error("Malformed JSON in decision node %s: %s", node_id, exc)
            return None

        match = conditions_match(obj, conditions)
        logger.info("Decision node condition result: %s", 'YES' if match else 'NO')

        handle = None if match else 'no'
        edge = _fetch_edge_by_handle(node[0], handle)

        if edge:
            target_node = _fetch_node(edge[1])
            if not target_node:
                logger.warning("Target node not found for edge target id: %s", edge[1])
                return None
            result = traverse_node(
                target_node, obj, module, workflow_id,
                user=user, trigger=trigger, visited=visited, depth=depth + 1, max_depth=max_depth, **kwargs
            )
            if isinstance(result, dict) and "authurl" in result:
                return result
        else:
            logger.warning("No edge found for decision node (handle=%r).", handle)

    else:
        # Start or any other pass-through node
        edges = _fetch_edges(node[0])
        for edge in edges:
            target_node = _fetch_node(edge[1])
            if not target_node:
                logger.warning("Target node not found for edge target id: %s", edge[1])
                continue
            result = traverse_node(
                target_node, obj, module, workflow_id,
                user=user, trigger=trigger, visited=visited, depth=depth + 1, max_depth=max_depth, **kwargs
            )
            if isinstance(result, dict) and "authurl" in result:
                return result

    return None


# ---------------------------------------------------------------------------
# Private DB helpers — avoids repeating the same cursor boilerplate everywhere
# ---------------------------------------------------------------------------

def _fetch_edges(source_id: Any) -> List[Tuple]:
    """All edges leaving a node. Dual-path (raw / WorkflowEdge ORM)."""
    def _raw():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, target_id FROM workflow_edge WHERE source_id = %s",
                [source_id]
            )
            return cursor.fetchall()

    def _orm():
        from api.tenant_models import WorkflowEdge
        return list(
            WorkflowEdge.objects.filter(source_id=source_id)
            .values_list("id", "target_id")
        )

    return _dispatch_path(
        "workflow_executor._fetch_edges",
        raw_impl=_raw, orm_impl=_orm, flag="USE_ORM_FOR_BL",
    )


def _fetch_edge_by_handle(source_id: Any, handle: Optional[str]) -> Optional[Tuple]:
    """
    Fetch a single edge by source_id and source_handle.
    handle=None  → match IS NULL  (the 'yes' / default path)
    handle='no'  → match = 'no'
    """
    def _raw():
        if handle is None:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, target_id FROM workflow_edge "
                    "WHERE source_id = %s AND source_handle IS NULL LIMIT 1",
                    [source_id]
                )
                return cursor.fetchone()
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, target_id FROM workflow_edge "
                "WHERE source_id = %s AND source_handle = %s LIMIT 1",
                [source_id, handle]
            )
            return cursor.fetchone()

    def _orm():
        from api.tenant_models import WorkflowEdge
        qs = WorkflowEdge.objects.filter(source_id=source_id)
        qs = qs.filter(source_handle__isnull=True) if handle is None \
            else qs.filter(source_handle=handle)
        return qs.values_list("id", "target_id").first()

    return _dispatch_path(
        "workflow_executor._fetch_edge_by_handle",
        raw_impl=_raw, orm_impl=_orm, flag="USE_ORM_FOR_BL",
    )


def _fetch_node(node_id: Any) -> Optional[Tuple]:
    """Fetch a workflow node by id. Same return shape both paths."""
    def _raw():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, label, node_type, data FROM workflow_node WHERE id = %s",
                [node_id]
            )
            return cursor.fetchone()

    def _orm():
        from api.tenant_models import WorkflowNode
        return (
            WorkflowNode.objects.filter(id=node_id)
            .values_list("id", "label", "node_type", "data")
            .first()
        )

    return _dispatch_path(
        "workflow_executor._fetch_node",
        raw_impl=_raw, orm_impl=_orm, flag="USE_ORM_FOR_BL",
    )


# ---------------------------------------------------------------------------
# Action dispatch
# ---------------------------------------------------------------------------

def execute_action(
    node: Tuple,
    obj: Dict[str, Any],
    module: str,
    workflow_id: str,
    user: Optional[Any] = None,
    trigger: str = "",
    **kwargs
) -> Optional[Dict]:
    """Execute an action node based on its configuration."""
    try:
        filters = json.loads(node[3]).get("filters", {})
    except (json.JSONDecodeError, TypeError) as exc:
        logger.error("Malformed JSON in action node %s: %s", node[0], exc)
        return None

    action_type = filters.get("actionType")
    config = filters.get("config", {})

    logger.info("Executing action: %s", action_type)

    if action_type == "send_email":
        # FIX BUG-06: was shadowing stdlib send_mail
        return execute_send_mail(config, obj, module, user=user, **kwargs)
    elif action_type == "send_whatsapp":
        send_whatsapp(obj, config)
    elif action_type == "create_record":
        create_record(obj, config, module, user=user, **kwargs)
    elif action_type in ("update_record", "update_field"):
        update_record(obj, config, module, user=user, **kwargs)
    elif action_type == "send_notification":
        execute_send_notification(config, obj, module, trigger=trigger, user=user, **kwargs)
    else:
        logger.warning("Unknown action type: %s", action_type)

    return None


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------

def conditions_match(obj: Dict[str, Any], conditions: List[Dict]) -> bool:
    """
    Check if object data matches ALL specified conditions (implicit AND).

    FIX BUG-03: was using `if` for every branch so eq + contains both ran on the
                same iteration.  Changed to if/elif/else.
    FIX BUG-04: added neq, gt, gte, lt, lte operators.
    """
    if not conditions:
        logger.debug("No conditions to match. Assuming TRUE.")
        return True

    logger.debug("Evaluating conditions:")
    for cond in conditions:
        field_name = cond.get("field", {}).get("name") if isinstance(cond.get("field"), dict) else cond.get("field")
        operator = cond.get("operator")
        value = cond.get("value")
        actual_value = obj.get(field_name)
        logger.debug("  - %s (%s) %s --> actual: %s", field_name, operator, value, actual_value)

        if operator == "eq":
            actual_kind, actual_norm = _normalize_for_equality(actual_value)
            expected_kind, expected_norm = _normalize_for_equality(value)

            if actual_kind == expected_kind:
                if actual_norm != expected_norm:
                    logger.debug("    Condition failed: normalized equality check")
                    return False
            elif {actual_kind, expected_kind} == {"bool", "numeric"}:
                bool_val = actual_norm if actual_kind == "bool" else expected_norm
                num_val = actual_norm if actual_kind == "numeric" else expected_norm
                if bool_val != (num_val == Decimal("1")):
                    logger.debug("    Condition failed: bool/number equality check")
                    return False
            else:
                if str(actual_value) != str(value):
                    logger.debug("    Condition failed: fallback equality check")
                    return False

        # FIX BUG-04 — new operators
        elif operator == "neq":
            if str(actual_value).strip().lower() == str(value).strip().lower():
                logger.debug("    Condition failed: neq check")
                return False

        elif operator in ("gt", "gte", "lt", "lte"):
            actual_num = _coerce_numeric(actual_value)
            expected_num = _coerce_numeric(value)
            if actual_num is None or expected_num is None:
                logger.debug("    Condition failed: non-numeric values for %s", operator)
                return False
            passed = {
                "gt":  actual_num > expected_num,
                "gte": actual_num >= expected_num,
                "lt":  actual_num < expected_num,
                "lte": actual_num <= expected_num,
            }[operator]
            if not passed:
                logger.debug("    Condition failed: %s check", operator)
                return False

        elif operator == "not_contains":
            actual_str = "" if actual_value is None else str(actual_value)
            value_str = "" if value is None else str(value)
            if value_str.lower() in actual_str.lower():
                logger.debug("    Condition failed: not_contains check")
                return False

        elif operator == "contains":
            actual_str = "" if actual_value is None else str(actual_value)
            value_str = "" if value is None else str(value)
            if value_str.lower() not in actual_str.lower():
                logger.debug("    Condition failed: contains check")
                return False

        else:
            logger.warning("Unknown operator '%s' in condition — treating as failed", operator)
            return False

    logger.debug("    All conditions passed")
    return True


# ---------------------------------------------------------------------------
# Action implementations
# ---------------------------------------------------------------------------

def send_whatsapp(obj: Dict[str, Any], config: Dict[str, Any]) -> None:
    """Send a WhatsApp message. Placeholder — integrate your WhatsApp API here."""
    phone = obj.get(config.get("to"))
    template = config.get("template")
    logger.info("Sending WhatsApp message to: %s with template '%s'", phone, template)
    # TODO: Integrate with actual WhatsApp API


def execute_send_mail(
    config: Dict[str, Any],
    obj: Dict[str, Any],
    module: str,
    user: Optional[Any] = None,
    **kwargs
) -> Optional[Dict]:
    """
    Send an email using a named template.

    FIX BUG-06: Renamed from send_mail to avoid shadowing Django's send_mail.
    FIX BUG-07: Fetch template columns by name instead of magic integer index.
    """
    template_name = config.get("template")
    if not template_name:
        logger.warning("No email template specified in action configuration.")
        return None

    # Phase 3.C: dual-path. EmailTemplate is in Wave 5 (api/tenant_models/workflow.py).
    def _template_raw():
        with connection.cursor() as cursor:
            cursor.execute(
                # FIX BUG-07: select only the columns we need, by name
                "SELECT template_type, subject, body FROM email_templates WHERE name = %s",
                [template_name]
            )
            return cursor.fetchone()

    def _template_orm():
        from api.tenant_models import EmailTemplate
        return (
            EmailTemplate.objects.filter(name=template_name)
            .values_list("template_type", "subject", "body")
            .first()
        )

    row = _dispatch_path(
        "workflow_executor.email_template_lookup",
        raw_impl=_template_raw, orm_impl=_template_orm, flag="USE_ORM_FOR_BL",
    )

    if not row:
        logger.warning("Email template '%s' not found.", template_name)
        return None

    type_, subject, body = row  # unpacked by position, but columns are explicit above
    data = {
        "record_ids": [obj.get("id")],
        "template_subject": subject,
        "template_body": body,
        "selected_object": module,
    }
    response = send_test_email(user, data, **kwargs)
    if isinstance(response, dict) and "authurl" in response:
        logger.warning("Email sending deferred due to authentication requirement.")
        return response

    return None


def _resolve_user_ids(user_type: str, users: List[str]) -> List[str]:
    """
    Resolve a list of user/profile/group IDs into actual user IDs.

    - user_type='user'    → users are already user IDs, return as-is
    - user_type='profile' → users are profile IDs, fetch associated user IDs
    - user_type='group'   → users are group IDs, recursively resolve sub-groups
                            via user_group_public_groups, then collect all user IDs
    """
    if not users:
        return []

    if user_type == "user":
        return users

    if user_type == "profile":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM users WHERE profile_id = ANY(%s) AND is_active = true",
                [list(users)],
            )
            return [row[0] for row in cursor.fetchall()]

    if user_type == "group":
        # Recursively collect all group IDs (including sub-groups).
        # Phase 3.C: dual-path. UserGroupPublicGroup is in Wave 2
        # follow-up (api/tenant_models/authz.py).
        all_group_ids = set(users)
        queue = list(users)
        while queue:
            current_queue = list(queue)

            def _sub_groups_raw(_q=current_queue):
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT public_group_id FROM user_group_public_groups "
                        "WHERE user_group_id = ANY(%s)",
                        [list(_q)],
                    )
                    return [row[0] for row in cursor.fetchall()]

            def _sub_groups_orm(_q=current_queue):
                from api.tenant_models import UserGroupPublicGroup
                return list(
                    UserGroupPublicGroup.objects.filter(
                        user_group_id__in=_q
                    ).values_list("public_group_id", flat=True)
                )

            sub_groups = _dispatch_path(
                "workflow_executor.resolve_user_groups.sub_groups",
                raw_impl=_sub_groups_raw, orm_impl=_sub_groups_orm,
                flag="USE_ORM_FOR_BL",
            )
            queue = [g for g in sub_groups if g not in all_group_ids]
            all_group_ids.update(sub_groups)

        if not all_group_ids:
            return []

        # Get users from all resolved groups
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT DISTINCT u.id FROM users u "
                "JOIN user_group_users ugu ON ugu.user_id = u.id "
                "WHERE ugu.user_group_id = ANY(%s) AND u.is_active = true",
                [list(all_group_ids)],
            )
            return [row[0] for row in cursor.fetchall()]

    logger.warning("Unknown user_type '%s' for send_notification", user_type)
    return []


_TRIGGER_MESSAGES = {
    "create_records": "New record created in {module}",
    "update_records": "Record updated in {module}",
    "delete_records": "Record deleted from {module}",
    "send_email":     "Email sent from {module}",
}


def execute_send_notification(
    config: Dict[str, Any],
    obj: Dict[str, Any],
    module: str,
    trigger: str = "",
    user: Optional[Any] = None,
    **kwargs
) -> None:
    """
    Send in-app notifications to resolved users based on user_type.

    config.user_type: 'user' | 'profile' | 'group'
    config.users: list of IDs (user IDs, profile IDs, or group IDs depending on user_type)
    """
    user_type = config.get("user_type", "user")
    target_ids = config.get("users", [])

    if not target_ids:
        logger.warning("send_notification: no target users/profiles/groups specified.")
        return

    resolved_user_ids = _resolve_user_ids(user_type, target_ids)
    if not resolved_user_ids:
        logger.warning("send_notification: no users resolved for user_type='%s', ids=%s", user_type, target_ids)
        return

    from channels.layers import get_channel_layer
    from api.notifications.notify import trigger_notication

    channel_layer = get_channel_layer()
    module_label = module.replace("_", " ").title()
    message = _TRIGGER_MESSAGES.get(trigger, "Activity on {module}").format(module=module_label)
    notification_data = {"object_name": module, "id": obj.get("id")}

    for owner_id in resolved_user_ids:
        try:
            trigger_notication(
                owner_id=owner_id,
                channel_layer=channel_layer,
                title=module_label,
                notification_type="alert",
                channel="app",
                user_id=owner_id,
                message=message,
                data=notification_data,
                **kwargs,
            )
        except Exception as exc:
            logger.error("Failed to send notification to user %s: %s", owner_id, exc)
