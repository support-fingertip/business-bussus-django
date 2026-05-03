def convert_field_to_json(field_data):
    """
    Convert a dictionary representation of a Field model to a structured JSON format.
    """
    # Mapping of custom datatypes to Django ORM field types
    datatype_mapping = {
        "text": "CharField",
        "lookup_relationship": "ForeignKey",
        "phone": "CharField",
        "email": "EmailField",
        "longtext": "TextField",
        "encrypted_text": "CharField",
        "geo_location": "CharField",
        "currency": "DecimalField",
        "number": "IntegerField",
        "url": "URLField",
        "picklist": "CharField",
        "multipicklist": "TextField",
        "checkbox": "BooleanField"
    }

    # Extract data safely using `.get()`
    datatype = field_data.get("datatype", "text").lower()  # Default to "text" if missing
    django_field_type = datatype_mapping.get(datatype, "CharField")

    field_json = {
        "name": field_data.get("name"),
        "field_type": django_field_type,
        "options": {
            "max_length": field_data.get("length", 255),  # Default max_length 255
            "unique": field_data.get("unique_field", False),
            "null": not field_data.get("required", False),  # Null=True if not required
            "blank": True,  # Assuming blank is always allowed unless required
        }
    }

    # If the field type is IntegerField, DecimalField, or ForeignKey, remove `max_length`
    if django_field_type in ["IntegerField", "DecimalField", "ForeignKey", "BooleanField"]:
        field_json["options"].pop("max_length", None)

    # If it's a ForeignKey (lookup relationship), add `related_model`
    if django_field_type == "ForeignKey":
        field_json["options"].pop("unique", None)  # ForeignKey is not unique by default
        field_json["options"]["related_model"] = field_data.get("parent_object", "Unknown")        

    return field_json
