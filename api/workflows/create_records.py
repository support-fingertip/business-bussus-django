"""
Create records workflow action.

FIX SUMMARY:
  [BUG-21]  process_formula() returns typed values (date, datetime, numbers) after
            BUG-17 fix, but create_record was logging the result before it was
            assigned.  Moved the debug log to after assignment.
  [BUG-22]  value_type fallback (the else branch) silently accepted any unknown
            valueType string as a literal — added a warning so bad configs are
            surfaced in logs.
"""
import logging
import re
from typing import Any, Dict, List, Optional

from api.ORM.sqlFunctions.createSQLFunction import post_data_sql
from api.formulas.evaluate_formula import process_formula

logger = logging.getLogger(__name__)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(value: Optional[str], field: str) -> str:
    if not value or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"Invalid identifier for {field}: '{value}'")
    return value


def create_record(
    obj: Dict[str, Any],
    config: Dict[str, Any],
    module: str,
    user: Optional[Any] = None,
    **kwargs,
) -> None:
    """
    Create a new record based on workflow configuration.

    Args:
        obj: The source object data
        config: Configuration for record creation including target object and field mappings
        module: The module name
        user: The user creating the record
        **kwargs: Additional context
    """
    target_object = _validate_identifier(config.get("object"), "object")
    extra_fields = config.get("extraFields", [])
    if not isinstance(extra_fields, list):
        raise ValueError("extraFields must be a list of field mappings")

    logger.info("Creating record in object '%s' with %d extraFields", target_object, len(extra_fields))

    data: Dict[str, Any] = {}

    for field_info in extra_fields:
        if not isinstance(field_info, dict):
            raise ValueError("Each extraField must be an object")

        field_name = _validate_identifier(field_info.get("name"), "field name")
        value_type = (field_info.get("valueType") or "").lower()
        value_ref = field_info.get("value")

        if value_type == "field":
            data[field_name] = obj.get(value_ref)
        elif value_type == "formula":
            formula_result = process_formula(value_ref, field_name, obj)
            # FIX BUG-21: log after assignment
            logger.debug("Formula result for field '%s': %s", field_name, formula_result)
            data[field_name] = formula_result
        elif value_type in {"text", "static", "literal", "number", "date", "datetime", ""}:
            # FIX BUG-22: empty string value_type treated as literal (backward-compatible)
            if not value_type:
                logger.warning(
                    "Field '%s' has no valueType — treating value as literal", field_name
                )
            data[field_name] = value_ref
        else:
            logger.warning(
                "Field '%s' has unsupported valueType '%s' — skipping", field_name, value_type
            )
            continue

    try:
        logger.info("Creating record in %s with data: %s", target_object, data)
        result = post_data_sql(
            target_object,
            data,
            user=user,
            section=f"Create - Record in {target_object}",
            enable_lookup_validation=True,
            **kwargs,
        )
        logger.info("Record created successfully: %s", result)
    except Exception as e:
        logger.error("Failed to create record: %s", e, exc_info=True)
        raise
