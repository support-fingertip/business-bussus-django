"""
Update records workflow action.

FIX SUMMARY:
  [BUG-23]  The parameter was named `object` — a Python builtin shadow.  Renamed
            to `obj` throughout (matching create_records.py convention).
  [BUG-24]  Formula result debug log was printed before data[field_name] assignment.
            Moved after assignment (mirrors BUG-21 fix in create_records).
"""
import logging
import re
from typing import Any, Dict, Optional

from api.ORM.sqlFunctions.updateSQLFunction import updateRawSQL
from api.formulas.evaluate_formula import process_formula

logger = logging.getLogger(__name__)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def update_record(
    obj: Dict[str, Any],   # FIX BUG-23: was named `object` (builtin shadow)
    config: Dict[str, Any],
    module: str,
    user: Optional[Any] = None,
    **kwargs,
) -> None:
    """
    Update an existing record based on workflow configuration.

    Args:
        obj: The object data to update
        config: Configuration for record update including field mappings
        module: The module name
        user: The user updating the record
        **kwargs: Additional context
    """
    if not _IDENTIFIER_RE.fullmatch(module or ""):
        raise ValueError(f"Invalid module name: {module}")

    extra_fields = config.get("extraFields", []) or []

    logger.info("Updating record in object '%s' with %d extraFields", module, len(extra_fields))
    data: Dict[str, Any] = {}

    for field_info in extra_fields:
        if not isinstance(field_info, dict):
            logger.warning("Skipping extraField that is not a dict: %s", field_info)
            continue

        field_name = field_info.get("name")
        value_type = (field_info.get("valueType") or "text").lower()
        value_ref = field_info.get("value")

        if not field_name or not _IDENTIFIER_RE.fullmatch(str(field_name)):
            logger.warning("Skipping field with invalid name: %s", field_name)
            continue

        if value_type == "field":
            data[field_name] = obj.get(value_ref)
        elif value_type == "formula":
            formula_result = process_formula(value_ref, field_name, obj)
            # FIX BUG-24: log after assignment
            logger.debug("Formula result for field '%s': %s", field_name, formula_result)
            data[field_name] = formula_result
        elif value_type in {"text", "static", "literal", "number", "date", "datetime"}:
            data[field_name] = value_ref
        else:
            logger.warning(
                "Skipping field '%s' due to unsupported valueType '%s'", field_name, value_type
            )
            continue

    record_id = obj.get("id")
    if record_id is None:
        raise ValueError("Object missing 'id'; cannot perform update")

    data["id"] = record_id
    logger.debug("Update data: %s", data)

    try:
        result = updateRawSQL(
            object_name=module,
            update_data=data,
            user=user,
            section=f"Update - {module}",
            enable_lookup_validation=True,
            **kwargs,
        )
        logger.info("Record updated successfully: %s", result)
    except Exception as e:
        logger.error("Failed to update record: %s", e, exc_info=True)
        raise
