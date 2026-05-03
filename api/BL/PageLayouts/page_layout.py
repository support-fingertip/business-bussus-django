from api.permissions.permissions import get_permissions
from api.security.schema_authority import get_validated_schema
from django.db import connection

from pprint import pprint

def PageLayouts(request, **kwargs):    
    def get_related_lists(object_name):
        related_fields = get_permissions(request, tableName='fields', fields=['name', 'label','object.name', 'object.label', 'object.id'], 
                        where=[{"field": "parent_object", "operator": "=", "value": object_name}], **kwargs).get('data')
        related_lists = [
            {"object": {"name": "file", "label": "Files", "id": "file_id"}, "fields": [], "related_field": {"name": "record_id", "label": "File", "id": "file_record_id", "datatype": "file"}},
            {"object": {"name": "field_history_log", "label": "Field History", "id": "field_history_log_id"}, "fields": [], "related_field": {"name": "record_id", "label": "Field History", "id": "field_history_log_id", "datatype": "records"}},
        ]
        # Only add email related list if the object has a field with datatype 'email'
        object_fields = get_permissions(request, tableName='fields', where=[{"field": "object.name", "operator": "=", "value": object_name}], fields=['name', 'label', 'datatype', 'id'], **kwargs).get('data', [])
        has_email_field = any(field.get('datatype') == 'email' for field in object_fields)
        if has_email_field:
            email_fields = get_permissions(request, tableName='fields', where=[{"field": "object_name", "operator": "=", "value": "email"}], fields=['id', 'name', 'label', 'object.id', 'object.name', 'object.label'], **kwargs).get('data', [])
            related_lists.append(
                {"object": {"name": "email", "label": "Email", "id": "email_id"}, "fields": email_fields, "related_field": {"name": "matched_record_id", "label": "Email", "id": "email_id", "datatype": "records"}}
            )
        for field in related_fields:
            fields_ = get_permissions(request, tableName='fields', where=[{"field": "object_name", "operator": "=", "value": field.get('object', {}).get('name')}], fields=['name', 'label', 'datatype', 'id'], **kwargs).get('data')
            for field_ in fields_:
                field_['visible'] = True if field_.get('name') == 'name' else False
            related_lists.append(
                {
                    "object": field.get('object', {}),
                    "fields": fields_,
                    "related_field": {
                        "name": field.get('name'),
                        "label": field.get('label'),
                        "id": field.get('id'),
                        "datatype": field.get('datatype')
                    }
                }
            )
        # datas = [rl for rl in related_lists if rl.get('object', {}).get('name') != object_name]
        return [rl for rl in related_lists if rl.get('object', {}).get('name') != object_name]
    object_name_ = request.GET.get('object_name')
    id = request.GET.get('id')
    created = request.GET.get('created')
    if object_name_ and not id and not created:
        result = get_permissions(request, tableName='page_layouts', where = [{"field": "object_name", "operator": "=", "value": object_name_}],fields=['name', 'label','created_by','created_date','last_modified_date'], **kwargs)
        try:
            schema = (get_validated_schema(kwargs) or 'public')
            for record in result.get('data', []):
                with connection.cursor() as cursor:
                    cursor.execute("SET search_path TO %s", [schema])
                    created_by_id = record.get("created_by")
                    if created_by_id:
                        cursor.execute("SELECT name FROM users WHERE id = %s", [created_by_id])
                        row = cursor.fetchone()
                        record["created_by"] = row[0] if row else None
                    last_modified_by_id = record.get("last_modified_by_id")
                    if last_modified_by_id:
                        cursor.execute("SELECT name FROM users WHERE id = %s", [last_modified_by_id])
                        row = cursor.fetchone()
                        record["last_modified_by"] = row[0] if row else None
        except Exception as e:
            pass 
        return result.get('data')                

    # Case 2: Creating a new page layout (Return default structure)
    elif object_name_ and created == "new":
        filters = [{"field": "object.name", "operator": "=", "value": object_name_}]
        fields = get_permissions(request, tableName='fields', where=filters, fields=['name', 'label'], **kwargs).get('data')
        response = {
            "palette": {
            "Fields": [{"id": "section", "name": "section", "label": "Section"}]+fields,             
                "Buttons": [],
                "CustomLinks": [],
                "QuickActions": [],
                "MobileLightningActions": [],
                "ExpandedLookups": [],
                "RelatedLists": get_related_lists(object_name_)
            },
            "layout": {
                "sections": [{
                "id": "section_1",
                "title": "New Section",
                "fields": []
                }],
                "relatedLists": [],
                "buttons": [],
                "name": "new_layout",
                "label": "New Layout",
                "object_name": object_name_
                
            }
        }
        return response
    elif not id and not object_name_:
        return {"error": "Both 'id' and 'object_name' are required."}
    page_layout = get_permissions(request, tableName='page_layouts', id=id,fields=['id', 'name', 'label', 'object_name', 'sections', 'related_lists'], **kwargs).get('data')[0]
    if not page_layout:
        return {"error": f"Page Layout with ID {id} not found."}
    object_name = page_layout.get('object_name')                
    filters = [{"field": "object.name", "operator": "=", "value": object_name}]
    fields = get_permissions(request, tableName='fields', where=filters, fields=['name', 'label'], **kwargs).get('data')
    palette =  {}

    # Build a set of object names that are already saved in this layout's related_lists
    saved_related_lists = page_layout.get("related_lists", []) or []
    saved_object_names = {
        item.get("object", {}).get("name")
        for item in saved_related_lists
        if item.get("object", {}).get("name")
    }

    # Mark each palette related-list item as is_added if already present in saved layout
    all_palette_related = get_related_lists(object_name)
    for item in all_palette_related:
        item["is_added"] = item.get("object", {}).get("name") in saved_object_names

    formatted_palette = {
        "Fields": [{"id": "section", "name": "section", "label": "Section"}] + fields,
        "Buttons": palette.get("Buttons", []),
        "CustomLinks": palette.get("CustomLinks", []),
        "QuickActions": palette.get("QuickActions", []),
        "MobileLightningActions": palette.get("MobileLightningActions", []),
        "ExpandedLookups": palette.get("ExpandedLookups", []),
        "RelatedLists": all_palette_related
    }                
    sections = page_layout.get("sections", [])               
    
    # Build lookup dict by name for O(1) access
    field_lookup = {field['name']: field for field in fields}

    for i, section in enumerate(sections):
        fields_ = section.get('fields', [])
        selected_fields = []
        for field_name in fields_:
            field = field_lookup.get(field_name)
            if field:
                selected_fields.append({
                    "id": field.get('id'),
                    "name": field.get('name'),
                    "label": field.get('label'),
                })
        section['id'] = f'section_{i+1}'
        section['fields'] = selected_fields                               
            
    # Step 5: Format the layout data
    layout = page_layout.get('layout') or {}  # Ensure it's empty if not available
    formatted_layout = {
        "sections": sections,
        "relatedLists": page_layout.get("related_lists", []),
        "buttons": page_layout.get("buttons", []),
        "id": page_layout.get("id"),
        "name": page_layout.get("name"),
        "label": page_layout.get("label"),
        "object_name": page_layout.get("object_name"),
    }

    response_data = {
        # "message": "Page Layout retrieved successfully.",
        "id": page_layout.get('id'),
        'name': page_layout.get('name'),
        "label": page_layout.get('label'),
        "palette": formatted_palette,
        "layout": formatted_layout
    }
    return response_data


    