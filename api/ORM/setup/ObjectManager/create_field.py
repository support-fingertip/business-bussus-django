import json
import random
import uuid
from django.db import transaction, connection
from api.ORM.AuditLogs.audit_trail_logs import log_audit
from api.ORM.setup.ObjectManager.field_execution import add_field_to_table
from api.formulas.formula_validation import validate_formula_syntax

def create_field(data, user=None, section=None, **kwargs):
    schema = kwargs.get('schema', 'public')
    field = data.get('field')
    profiles = data.get('profiles')
    pagelayouts = data.get('page_layouts')
    object_name = data.get('object')
    object_name = field.get('object_name')
    field_name = field.get('name')
    field_type = field.get('datatype', "text")
    required = field.get('required', False)
    unique = field.get('unique_field', False)
    label = field.get('label')
    pickup_values = field.get('pickup_values')  # assumed to be list or JSON
    parent_object = field.get('parent_object')
    starting_number = field.get('starting_number', 1000000)
    default_value_in_checkbox = field.get('default_value_in_checkbox', False)
    length = field.get('length', 255)  # Default length for text fields
    number_length = field.get('number_length', None)
    decimal_places = field.get('decimal_places', None)
    description = field.get('description', None)
    help_text = field.get('help_text', None)
    visible_lines = field.get('visible_lines', 1)  # Default to 1 line for text fields
    relationship_name = field.get('relationship_name', None)
    display_format = field.get('display_format', None)
    sendEmail = field.get('sendEmail', None)
    no_skip = field.get('no_skip', False)
    no_rollback = field.get('no_rollback', False)
    # Formula field properties
    formula_expression = field.get('formula_expression', None)
    formula_return_type = field.get('formula_return_type', None)
    # Roll-up summary field properties
    summarized_object = field.get('rollup_object', None) or field.get('summarized_object', None) or field.get('parent_object', None)
    rollup_type = field.get('rollup_type', None) or field.get('rollupType', None)
    field_to_aggregate = field.get('rollup_field', None) or field.get('field_to_aggregate', None)
    filter_criteria = field.get('rollup_filter_criteria', None) or field.get('filter_criteria', None)
    # Auto-generated fields cannot be required
    if field_type in ('auto_number', 'formula', 'rollup_summary'):
        required = False
    default_value = ""
    sort_alpha = False
    first_as_default = False
    limit_predefined_values = False
    if field_type in ['picklist', 'picklist_multi']:
        sort_alpha = field.get('sort_alpha', False)
        first_as_default = field.get('first_as_default', False)
        limit_predefined_values = field.get('limit_predefined_values', False)
        if first_as_default and pickup_values and isinstance(pickup_values, list):
            default_value = pickup_values[0]
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO %s", [schema])
                add_field_to_table(schema, field) 
                # Get object ID by name
                cursor.execute("SELECT id FROM object WHERE name = %s", [object_name])
                result = cursor.fetchone()
                if not result:
                    raise Exception(f"Object '{object_name}' does not exist.")
                object_id = result[0]

                # Check for existing field
                cursor.execute("SELECT COUNT(*) FROM fields WHERE object_id = %s AND name = %s", [object_id, field_name])
                if cursor.fetchone()[0] > 0:
                    raise Exception(f"Field '{field_name}' already exists in object '{object_name}'")

                # Validate formula expression
                if field_type == 'formula':
                    if not formula_expression:
                        raise Exception(f"Formula expression is required for formula field '{field_name}'")
                    if not formula_return_type:
                        raise Exception(f"Formula return type is required for formula field '{field_name}'")
                    validate_formula_syntax(formula_expression, field_name)

                # Validate roll-up summary fields
                if field_type == 'rollup_summary':
                    if not summarized_object:
                        raise Exception(f"Summarized object is required for roll-up summary field '{field_name}'")
                    if not rollup_type:
                        raise Exception(f"Rollup type is required for roll-up summary field '{field_name}'")
                    if rollup_type not in ['COUNT', 'SUM', 'MIN', 'MAX']:
                        raise Exception(f"Invalid rollup type '{rollup_type}'. Must be one of: COUNT, SUM, MIN, MAX")
                    if rollup_type in ['SUM', 'MIN', 'MAX'] and not field_to_aggregate:
                        raise Exception(f"Field to aggregate is required for rollup type '{rollup_type}'")

                # Insert into fields
                field_id = uuid.uuid4().hex[:10]
                cursor.execute("""
                    INSERT INTO fields (id, object_id, name, unique_field,
                                        datatype, required, label, pickup_values,
                                        parent_object, starting_number, default_value_in_checkbox, length,
                                        description, help_text, visible_lines, relationship_name,
                                        object_name, default_value,sort_alpha, first_as_default,
                                        limit_predefined_values,display_format,decimal_places,number_length,
                                        send_mail,no_skip,no_rollback,
                                        formula_expression, formula_return_type,
                                        summarized_object, rollup_type, field_to_aggregate, filter_criteria
                               )
                    VALUES (%s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s,
                            %s, %s, %s, %s)
                """, [
                    field_id, object_id, field_name,
                    unique, field_type, required,
                    label, pickup_values, parent_object,
                    starting_number, default_value_in_checkbox, length,
                    description, help_text, visible_lines,
                    relationship_name, object_name, default_value,
                    sort_alpha,first_as_default, limit_predefined_values,
                    display_format, decimal_places, number_length,
                    sendEmail, no_skip, no_rollback,
                    formula_expression, formula_return_type,
                    summarized_object, rollup_type, field_to_aggregate,
                    json.dumps(filter_criteria) if filter_criteria else None
                ])

                # Insert field permissions based on profiles
                for profile in profiles:
                    profile_id = profile.get('id')

                    # Validate read_access, set None if invalid or not bool
                    read_access = profile.get('read_access')
                    if not isinstance(read_access, bool):
                        read_access = False

                    # Validate edit_access, set None if invalid or not bool
                    edit_access = profile.get('edit_access')
                    if not isinstance(edit_access, bool):
                        edit_access = False

                    cursor.execute("""
                        INSERT INTO field_permissions (id, fields_id, object_id, profile_id, read_access, edit_access, read_only, visible)
                        VALUES (%s, %s, %s, %s, %s, %s, TRUE, TRUE)
                    """, [uuid.uuid4().hex[:10], field_id, object_id, profile_id, read_access, edit_access])


                # Update page layouts
                layouts_to_update = pagelayouts or []
                
                # If required, ensure it's added to default_layout even if not explicitly provided
                if required:
                    if not any(l.get('name') == 'default_layout' or l.get('label') == f"{object_name} Page Layout" for l in layouts_to_update):
                        layouts_to_update.append({'name': 'default_layout', 'label': f"{object_name} Page Layout"})

                if layouts_to_update:
                    for layout in layouts_to_update:
                        layout_name = layout.get('name')
                        layout_label = layout.get('label')
                        cursor.execute("SELECT id, sections FROM page_layouts WHERE object_name = %s AND (name = %s OR label = %s)", [object_name, layout_name, layout_label])
                        row = cursor.fetchone()
                        if row:
                            layout_id, sections = row
                            sections = json.loads(sections) if sections else []

                            # Add to 'Basic Information' section or create it
                            section_found = False
                            for sec in sections:
                                if sec.get("title") == "Basic Information":
                                    if field_name not in sec.get("fields", []):
                                        sec.setdefault("fields", []).append(field_name)
                                    section_found = True
                                    break
                            if not section_found:
                                sections.append({"title": "Basic Information", "fields": [field_name]})

                            cursor.execute("UPDATE page_layouts SET sections = %s WHERE id = %s", [json.dumps(sections), layout_id])
                
                # Update search_layouts
                cursor.execute("SELECT id, search_results_fields, lookup_dialog_fields, recent_items_fields FROM search_layouts WHERE object_id = %s", [object_id])
                row = cursor.fetchone()
                if row:
                    layout_id, search_fields, lookup_fields, recent_fields = row

                    search_fields = json.loads(search_fields) if search_fields else []
                    lookup_fields = json.loads(lookup_fields) if lookup_fields else []
                    recent_fields = json.loads(recent_fields) if recent_fields else []

                    if len(search_fields) < 5:
                        search_fields.append(field_name)
                    if len(lookup_fields) < 4:
                        lookup_fields.append(field_name)
                    if len(recent_fields) < 4:
                        recent_fields.append(field_name)

                    cursor.execute("""
                        UPDATE search_layouts
                        SET search_results_fields = %s,
                            lookup_dialog_fields = %s,
                            recent_items_fields = %s
                        WHERE id = %s
                    """, [
                        json.dumps(search_fields),
                        json.dumps(lookup_fields),
                        json.dumps(recent_fields),
                        layout_id
                    ])    
                log_audit(
                    f"Created field {field_name} of type {field_type} in object {object_name}",
                    f"Field Creation - {object_name}",
                    **kwargs
                )
    except Exception as e:
        raise Exception(str(e))
    return {
        "success": True,
        "message": f"Field '{field_name}' added successfully to object '{object_name}' and updated layouts.",
        "object_name":object_name,
        "field":field_name
    }