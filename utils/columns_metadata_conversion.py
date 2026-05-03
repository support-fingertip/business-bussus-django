def field_to_columns_metadata(payload: dict, object_name: str) -> dict:
    datatype_map = {
        "text": "VARCHAR(255)",
        "textarea": "TEXT",
        "textarealong": "TEXT",
        "number": f"NUMERIC({payload.get('number_length', 10)})",
        "checkbox": "BOOLEAN",
        "currency": "NUMERIC(10,2)",
        "date": "DATE",
        "datetime": "TIMESTAMP",
        "email": "VARCHAR(255)",
        "percent": "NUMERIC(5,2)",
        "phone": "VARCHAR(20)",
        "picklist": "TEXT",
        "multi_picklist": "TEXT",
        "text_encrypted": "TEXT",
        "time": "TIME",
        "geolocation": "TEXT",
        "url": "VARCHAR(255)",
        "rating": "INTEGER",
        "html": "TEXT",
        "image": "TEXT",
        "file": "TEXT",
        "auto_number": "TEXT",  # Store as TEXT with special default
        "formula": "TEXT",
        "lookup_relationship": 'VARCHAR(64)',
        "master_detail_relationship": "VARCHAR(64)",
        "rollup_summary": "TEXT",
    }

    raw_type = payload.get("datatype", "text")
    field_type = datatype_map.get(raw_type, "TEXT")
    name = payload.get("name")
    seq_name = None

    if raw_type == "checkbox":
        if payload.get("default_value_in_checkbox") == "unchecked":
            default_value = "FALSE"
        else:
            default_value = "TRUE"

    elif raw_type == "auto_number":
        seq_name = f"sequence_{name}{object_name}"
        display_format = payload.get("display_format", object_name[:3])
        default_value = f"('{display_format}-' || LPAD(nextval('{seq_name}')::text, 5, '0'))"


    else:
        default_value = None

    return {
        "table_name": object_name,
        "field_name": payload.get("name"),
        "label": payload.get("label"),
        "field_type": field_type,
        "is_nullable": not payload.get("required", False),
        "is_unique": payload.get("unique_field", False),
        "default_value": default_value,
        "references_table": payload.get('parent_object'),
        "references_field": 'id',
        "sort_order": 0,
        "is_created": False,
        "sequence_name": seq_name,
        "sequence_start": payload.get('starting_number', 100000)
    }
