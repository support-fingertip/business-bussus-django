"""
Roll-up summary field evaluation.

Computes aggregated values (COUNT, SUM, MIN, MAX) from a child object's records
filtered by optional criteria. Supports aggregating formula fields (no physical
column) by fetching child records and computing in Python.
"""
import json
from typing import Any, Dict, List, Optional

from django.db import connection
from psycopg2 import sql

from api.formulas.logger_config import get_logger

logger = get_logger(__name__)


def _is_formula_field(summarized_object: str, field_name: str, schema: str) -> Optional[str]:
    """Check if a field is a formula field. Returns formula_expression if yes, None otherwise."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO %s", [schema])
            cursor.execute("""
                SELECT f.formula_expression
                FROM fields f
                JOIN object o ON f.object_id = o.id
                WHERE o.name = %s AND f.name = %s AND f.datatype = 'formula'
            """, [summarized_object, field_name])
            row = cursor.fetchone()
            return row[0] if row else None
    except Exception:
        return None


def _fetch_child_records(
    summarized_object: str,
    parent_field: str,
    record_id: str,
    filter_criteria: Any,
    schema: str,
) -> List[Dict[str, Any]]:
    """Fetch all child records matching the parent and filter criteria."""
    with connection.cursor() as cursor:
        cursor.execute("SET search_path TO %s", [schema])

        where_parts = [sql.SQL("{} = %s").format(sql.Identifier(parent_field))]
        params = [record_id]

        filters = _parse_filter_criteria(filter_criteria)
        for f in filters:
            field = f.get("field")
            operator = f.get("operator", "=")
            value = f.get("value")
            if not field:
                continue
            valid_operators = {"=", "!=", ">", "<", ">=", "<=", "LIKE", "ILIKE", "IN", "NOT IN"}
            # Handle null/blank operators (no value needed)
            if operator in ("is_null", "is null"):
                where_parts.append(sql.SQL("{} IS NULL").format(sql.Identifier(field)))
                continue
            if operator in ("is_not_null", "is not null"):
                where_parts.append(sql.SQL("{} IS NOT NULL").format(sql.Identifier(field)))
                continue
            if operator in ("is_blank", "is blank"):
                where_parts.append(sql.SQL("({} IS NULL OR {} = '')").format(
                    sql.Identifier(field), sql.Identifier(field)))
                continue
            if operator in ("is_not_blank", "is not blank"):
                where_parts.append(sql.SQL("({} IS NOT NULL AND {} != '')").format(
                    sql.Identifier(field), sql.Identifier(field)))
                continue
            if operator.upper() not in valid_operators:
                continue
            where_parts.append(
                sql.SQL("{} {} %s").format(sql.Identifier(field), sql.SQL(operator))
            )
            params.append(value)

        where_clause = sql.SQL(" AND ").join(where_parts)
        query = sql.SQL("SELECT * FROM {} WHERE {}").format(
            sql.Identifier(summarized_object),
            where_clause,
        )
        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def evaluate_rollup(
    record_id: str,
    summarized_object: str,
    rollup_type: str,
    field_to_aggregate: Optional[str],
    filter_criteria: Any,
    parent_object: str,
    parent_field: str,
    schema: str = "public",
) -> Any:
    """
    Evaluate a single roll-up summary field.

    Supports both physical columns and formula fields on the child table.
    For formula fields, fetches child records and computes values in Python.
    """
    if rollup_type not in ("COUNT", "SUM", "MIN", "MAX"):
        raise ValueError(f"Invalid rollup_type: {rollup_type}")

    if rollup_type in ("SUM", "MIN", "MAX") and not field_to_aggregate:
        raise ValueError(f"field_to_aggregate is required for rollup_type '{rollup_type}'")

    try:
        # Check if field_to_aggregate is a formula field (no physical column)
        formula_expr = None
        if field_to_aggregate:
            formula_expr = _is_formula_field(summarized_object, field_to_aggregate, schema)

        if formula_expr or rollup_type == "COUNT":
            # Fetch child records and compute in Python
            child_records = _fetch_child_records(
                summarized_object, parent_field, record_id, filter_criteria, schema
            )

            if rollup_type == "COUNT":
                return len(child_records)

            # Evaluate formula for each child record
            from api.formulas.evaluate_formula import process_formula
            values = []
            for record in child_records:
                try:
                    val = process_formula(formula_expr, field_to_aggregate, record)
                    if val is not None:
                        values.append(float(val))
                except Exception:
                    continue

            if not values:
                return 0

            if rollup_type == "SUM":
                return round(sum(values),2)
            elif rollup_type == "MIN":
                return round(min(values),2)
            elif rollup_type == "MAX":
                return round(max(values),2)
        else:
            # Physical column — use SQL aggregation directly
            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO %s", [schema])

                agg_expr = sql.SQL("{}({})").format(
                    sql.SQL(rollup_type),
                    sql.Identifier(field_to_aggregate),
                )

                where_parts = [sql.SQL("{} = %s").format(sql.Identifier(parent_field))]
                params = [record_id]

                filters = _parse_filter_criteria(filter_criteria)
                for f in filters:
                    field = f.get("field")
                    operator = f.get("operator", "=")
                    value = f.get("value")
                    if not field:
                        continue
                    if operator in ("is_null", "is null"):
                        where_parts.append(sql.SQL("{} IS NULL").format(sql.Identifier(field)))
                        continue
                    if operator in ("is_not_null", "is not null"):
                        where_parts.append(sql.SQL("{} IS NOT NULL").format(sql.Identifier(field)))
                        continue
                    if operator in ("is_blank", "is blank"):
                        where_parts.append(sql.SQL("({} IS NULL OR {} = '')").format(
                            sql.Identifier(field), sql.Identifier(field)))
                        continue
                    if operator in ("is_not_blank", "is not blank"):
                        where_parts.append(sql.SQL("({} IS NOT NULL AND {} != '')").format(
                            sql.Identifier(field), sql.Identifier(field)))
                        continue
                    valid_operators = {"=", "!=", ">", "<", ">=", "<=", "LIKE", "ILIKE", "IN", "NOT IN"}
                    if operator.upper() not in valid_operators:
                        continue
                    where_parts.append(
                        sql.SQL("{} {} %s").format(sql.Identifier(field), sql.SQL(operator))
                    )
                    params.append(value)

                where_clause = sql.SQL(" AND ").join(where_parts)
                query = sql.SQL("SELECT {} FROM {} WHERE {}").format(
                    agg_expr,
                    sql.Identifier(summarized_object),
                    where_clause,
                )
                cursor.execute(query, params)
                result = cursor.fetchone()
                return result[0] if result and result[0] is not None else 0

    except Exception as e:
        logger.error("Rollup evaluation error: %s", e)
        raise


def evaluate_rollup_batch(
    record_ids: List[str],
    summarized_object: str,
    rollup_type: str,
    field_to_aggregate: Optional[str],
    filter_criteria: Any,
    parent_field: str,
    schema: str = "public",
) -> Dict[str, Any]:
    """
    Evaluate the same rollup spec for many parent IDs in a single SQL query.
    Returns {parent_id: aggregated_value}. Missing parents default to 0.
    """
    if rollup_type not in ("COUNT", "SUM", "MIN", "MAX"):
        raise ValueError(f"Invalid rollup_type: {rollup_type}")
    if rollup_type in ("SUM", "MIN", "MAX") and not field_to_aggregate:
        raise ValueError(f"field_to_aggregate is required for rollup_type '{rollup_type}'")
    if not record_ids:
        return {}

    # Deduplicate and keep only truthy ids
    unique_ids = list({rid for rid in record_ids if rid})
    if not unique_ids:
        return {}

    results: Dict[str, Any] = {rid: 0 for rid in unique_ids}

    try:
        formula_expr = None
        if field_to_aggregate:
            formula_expr = _is_formula_field(summarized_object, field_to_aggregate, schema)

        if formula_expr or rollup_type == "COUNT":
            # Formula child fields (or COUNT) — fetch child rows for all parents
            # in one query and aggregate per-parent in Python.
            from api.formulas.evaluate_formula import process_formula

            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO %s", [schema])
                where_parts = [sql.SQL("{} = ANY(%s)").format(sql.Identifier(parent_field))]
                params: List[Any] = [unique_ids]

                filters = _parse_filter_criteria(filter_criteria)
                for f in filters:
                    field = f.get("field")
                    operator = f.get("operator", "=")
                    value = f.get("value")
                    if not field:
                        continue
                    if operator in ("is_null", "is null"):
                        where_parts.append(sql.SQL("{} IS NULL").format(sql.Identifier(field)))
                        continue
                    if operator in ("is_not_null", "is not null"):
                        where_parts.append(sql.SQL("{} IS NOT NULL").format(sql.Identifier(field)))
                        continue
                    if operator in ("is_blank", "is blank"):
                        where_parts.append(sql.SQL("({} IS NULL OR {} = '')").format(
                            sql.Identifier(field), sql.Identifier(field)))
                        continue
                    if operator in ("is_not_blank", "is not blank"):
                        where_parts.append(sql.SQL("({} IS NOT NULL AND {} != '')").format(
                            sql.Identifier(field), sql.Identifier(field)))
                        continue
                    valid_operators = {"=", "!=", ">", "<", ">=", "<=", "LIKE", "ILIKE", "IN", "NOT IN"}
                    if operator.upper() not in valid_operators:
                        continue
                    where_parts.append(
                        sql.SQL("{} {} %s").format(sql.Identifier(field), sql.SQL(operator))
                    )
                    params.append(value)

                where_clause = sql.SQL(" AND ").join(where_parts)
                query = sql.SQL("SELECT * FROM {} WHERE {}").format(
                    sql.Identifier(summarized_object), where_clause,
                )
                cursor.execute(query, params)
                columns = [desc[0] for desc in cursor.description]
                children = [dict(zip(columns, row)) for row in cursor.fetchall()]

            bucketed: Dict[str, List[float]] = {rid: [] for rid in unique_ids}
            counts: Dict[str, int] = {rid: 0 for rid in unique_ids}
            for child in children:
                parent_id = child.get(parent_field)
                if parent_id not in bucketed:
                    continue
                counts[parent_id] += 1
                if rollup_type == "COUNT":
                    continue
                try:
                    val = process_formula(formula_expr, field_to_aggregate, child)
                    if val is not None:
                        bucketed[parent_id].append(float(val))
                except Exception:
                    continue

            if rollup_type == "COUNT":
                return counts
            for rid, vals in bucketed.items():
                if not vals:
                    results[rid] = 0
                elif rollup_type == "SUM":
                    results[rid] = round(sum(vals), 2)
                elif rollup_type == "MIN":
                    results[rid] = round(min(vals), 2)
                elif rollup_type == "MAX":
                    results[rid] = round(max(vals), 2)
            return results

        # Physical column — single SQL GROUP BY query
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO %s", [schema])
            agg_expr = sql.SQL("{}({})").format(
                sql.SQL(rollup_type), sql.Identifier(field_to_aggregate),
            )
            where_parts = [sql.SQL("{} = ANY(%s)").format(sql.Identifier(parent_field))]
            params: List[Any] = [unique_ids]

            filters = _parse_filter_criteria(filter_criteria)
            for f in filters:
                field = f.get("field")
                operator = f.get("operator", "=")
                value = f.get("value")
                if not field:
                    continue
                if operator in ("is_null", "is null"):
                    where_parts.append(sql.SQL("{} IS NULL").format(sql.Identifier(field)))
                    continue
                if operator in ("is_not_null", "is not null"):
                    where_parts.append(sql.SQL("{} IS NOT NULL").format(sql.Identifier(field)))
                    continue
                if operator in ("is_blank", "is blank"):
                    where_parts.append(sql.SQL("({} IS NULL OR {} = '')").format(
                        sql.Identifier(field), sql.Identifier(field)))
                    continue
                if operator in ("is_not_blank", "is not blank"):
                    where_parts.append(sql.SQL("({} IS NOT NULL AND {} != '')").format(
                        sql.Identifier(field), sql.Identifier(field)))
                    continue
                valid_operators = {"=", "!=", ">", "<", ">=", "<=", "LIKE", "ILIKE", "IN", "NOT IN"}
                if operator.upper() not in valid_operators:
                    continue
                where_parts.append(
                    sql.SQL("{} {} %s").format(sql.Identifier(field), sql.SQL(operator))
                )
                params.append(value)

            where_clause = sql.SQL(" AND ").join(where_parts)
            query = sql.SQL("SELECT {}, {} FROM {} WHERE {} GROUP BY {}").format(
                sql.Identifier(parent_field),
                agg_expr,
                sql.Identifier(summarized_object),
                where_clause,
                sql.Identifier(parent_field),
            )
            cursor.execute(query, params)
            for parent_id, val in cursor.fetchall():
                if parent_id in results:
                    results[parent_id] = val if val is not None else 0
        return results
    except Exception as e:
        logger.error("Batch rollup evaluation error: %s", e)
        return {rid: 0 for rid in unique_ids}


def _get_rollup_fields_metadata(parent_object: str, schema: str) -> List[Dict]:
    """Fetch roll-up summary field metadata from the fields table for a given object."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO %s", [schema])
            cursor.execute("""
                SELECT f.name, f.summarized_object, f.rollup_type,
                       f.field_to_aggregate, f.filter_criteria
                FROM fields f
                JOIN object o ON f.object_id = o.id
                WHERE o.name = %s AND f.datatype = 'rollup_summary'
            """, [parent_object])
            rows = cursor.fetchall()
            return [
                {
                    "name": row[0],
                    "summarized_object": row[1],
                    "rollup_type": row[2],
                    "field_to_aggregate": row[3],
                    "filter_criteria": row[4],
                }
                for row in rows
            ]
    except Exception as e:
        logger.error("Error fetching rollup fields metadata: %s", e)
        return []


def evaluate_rollup_fields(
    record_id: str,
    record_data: Dict[str, Any],
    parent_object: str,
    schema: str = "public",
) -> Dict[str, Any]:
    """
    Evaluate all roll-up summary fields for a record and inject values into record_data.

    Args:
        record_id: The parent record ID.
        record_data: The record dict to inject computed values into.
        parent_object: The parent object/table name.
        schema: Database schema name.

    Returns:
        The updated record_data with rollup values.
    """
    rollup_fields = _get_rollup_fields_metadata(parent_object, schema)

    for rollup_col in rollup_fields:
        fname = rollup_col.get("name")
        summarized_object = rollup_col.get("summarized_object")
        rollup_type = rollup_col.get("rollup_type")
        field_to_aggregate = rollup_col.get("field_to_aggregate")
        filter_criteria = rollup_col.get("filter_criteria")

        if not fname or not summarized_object or not rollup_type:
            continue

        # The foreign key on the child table pointing to the parent
        parent_field = f"{parent_object}_id"

        try:
            record_data[fname] = evaluate_rollup(
                record_id=record_id,
                summarized_object=summarized_object,
                rollup_type=rollup_type,
                field_to_aggregate=field_to_aggregate,
                filter_criteria=filter_criteria,
                parent_object=parent_object,
                parent_field=parent_field,
                schema=schema,
            )
        except Exception as e:
            logger.error("Rollup evaluation error for '%s': %s", fname, e)
            record_data[fname] = None
    return record_data


def _parse_filter_criteria(filter_criteria: Any) -> List[Dict]:
    """Parse filter_criteria from various formats into a list of filter dicts."""
    if not filter_criteria:
        return []
    if isinstance(filter_criteria, str):
        try:
            filter_criteria = json.loads(filter_criteria)
        except (json.JSONDecodeError, TypeError):
            return []
    if isinstance(filter_criteria, dict):
        return [filter_criteria]
    if isinstance(filter_criteria, list):
        return filter_criteria
    return []
