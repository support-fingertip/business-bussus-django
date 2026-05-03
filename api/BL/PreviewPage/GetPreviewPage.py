from api.permissions.permissions import get_permissions
from utils.field_tracking import get_field_history
from utils.target_item_filters import enrich_target_item_with_assigned_to


def get_preview_page(request, table, **kwargs):
    object_name = table  
    record_id = request.GET.get('id')              
    try: 
        object_details = get_permissions(request, tableName='object', where =[{'field': 'name', 'value': object_name, 'operator': '='}], **kwargs).get('data')[0]
    except Exception:
        raise Exception('Object not found.')  
           
    assigned_layouts = get_permissions(
        request,
        tableName='layout_assignment',
        where=[
            {"field": "object_id", "operator": "=", "value": object_details.get('id')},
            {"field": "profile_id", "operator": "=", "value":  kwargs.get('profile_id')}
        ],
        **kwargs
    ).get('data') 

    page_layout_id = assigned_layouts[0].get('page_layouts_id') if assigned_layouts else None
    if not page_layout_id:
        return {"error": "No layout assigned for this object."}

    layout_data = get_permissions(
        request,
        tableName='page_layouts',
        where=[
            {"field": "object_name", "operator": "=", "value": object_name},
            {"field": "id", "operator": "=", "value": page_layout_id}
        ],
        **kwargs
    ).get('data')

    if not layout_data:
        return {"error": "No layout found for this object."}

    layout = layout_data[0]
    sections = layout.get('sections', [])
    buttons = layout.get('buttons', [])
    field_items = layout.get('field_items', [])
    related_lists = layout.get("related_lists", [])

    if not record_id:
        return {
            "layout": sections
        }

    # --- Extract all fields needed from layout sections ---
    fields_to_fetch = set()
    for section in sections:
        fields_to_fetch.update(section.get("fields", []))

    # Convert set to list for passing
    fields_to_fetch = list(fields_to_fetch)
    if object_name in ["event", "events"]:
        # Required for reconstructing multi-attendee/account selections on refresh.
        for required_field in [
            "master_record_id",
            "leads_id",
            "contacts_id",
            "accounts_id",
            "subject",
            "start",
            "end",
            "owner_id",
            "created_by_id",
        ]:
            if required_field not in fields_to_fetch:
                fields_to_fetch.append(required_field)
    if object_name in ["lead", "leads"]:
        if not any(str(field_name).lower() == "company" for field_name in fields_to_fetch):
            fields_to_fetch.append("company")
    # --- Fetch main record data with only required fields ---
    result = get_permissions(
        request,
        tableName=object_name,
        id=record_id,
        fields=fields_to_fetch,
        **kwargs
    )          
    record_lists = result.get('data', [])
    all_columns = result.get('all_columns', [])
    record_data = record_lists[0] if record_lists else {}

    # Event records may be persisted as multiple sibling rows (attendee x account).
    # Aggregate sibling lookups so preview/edit can show full multi selections after refresh.
    if str(object_name).lower() in ["event", "events"] and record_data:
        group_id = record_data.get("master_record_id") or record_data.get("id")
        sibling_rows = []

        if group_id:
            sibling_rows = get_permissions(
                request,
                tableName='event',
                where=[
                    {"field": "is_deleted", "operator": "=", "value": False},
                    {"field": "master_record_id", "operator": "=", "value": group_id},
                ],
                fields=[
                    "id",
                    "leads_id",
                    "contacts_id",
                    "accounts_id",
                    "leads.id",
                    "leads.name",
                    "contacts.id",
                    "contacts.name",
                    "accounts.id",
                    "accounts.name",
                ],
                **kwargs
            ).get('data', [])

        # Fallback for legacy data where sibling events were created
        # without master_record_id linkage.
        if not sibling_rows:
            fallback_where = [{"field": "is_deleted", "operator": "=", "value": False}]

            if record_data.get("subject"):
                fallback_where.append({
                    "field": "subject",
                    "operator": "=",
                    "value": record_data.get("subject"),
                })
            if record_data.get("start"):
                fallback_where.append({
                    "field": "start",
                    "operator": "=",
                    "value": record_data.get("start"),
                })
            if record_data.get("end"):
                fallback_where.append({
                    "field": "end",
                    "operator": "=",
                    "value": record_data.get("end"),
                })
            if record_data.get("owner_id"):
                fallback_where.append({
                    "field": "owner_id",
                    "operator": "=",
                    "value": record_data.get("owner_id"),
                })
            if record_data.get("created_by_id"):
                fallback_where.append({
                    "field": "created_by_id",
                    "operator": "=",
                    "value": record_data.get("created_by_id"),
                })

            # Only attempt fallback when we have enough signal to avoid broad matches.
            if len(fallback_where) >= 4:
                sibling_rows = get_permissions(
                    request,
                    tableName='event',
                    where=fallback_where,
                    fields=[
                        "id",
                        "leads_id",
                        "contacts_id",
                        "accounts_id",
                        "leads.id",
                        "leads.name",
                        "contacts.id",
                        "contacts.name",
                        "accounts.id",
                        "accounts.name",
                    ],
                    **kwargs
                ).get('data', [])

        rows_for_aggregation = [record_data, *sibling_rows]

        def collect_ids(rows, key):
            values = []
            seen = set()
            for row in rows:
                value = row.get(key)
                if not value:
                    continue
                if value not in seen:
                    seen.add(value)
                    values.append(value)
            return values

        def collect_related(rows, key):
            values = []
            seen = set()
            for row in rows:
                related = row.get(key)
                if not isinstance(related, dict):
                    continue
                related_id = related.get("id")
                if not related_id or related_id in seen:
                    continue
                seen.add(related_id)
                values.append({
                    "id": related_id,
                    "name": related.get("name") or str(related_id),
                })
            return values

        aggregated_leads = collect_ids(rows_for_aggregation, "leads_id")
        aggregated_contacts = collect_ids(rows_for_aggregation, "contacts_id")
        aggregated_accounts = collect_ids(rows_for_aggregation, "accounts_id")

        record_data["leads_id"] = aggregated_leads
        record_data["contacts_id"] = aggregated_contacts
        record_data["accounts_id"] = aggregated_accounts

        related_leads = collect_related(rows_for_aggregation, "leads")
        related_contacts = collect_related(rows_for_aggregation, "contacts")
        related_accounts = collect_related(rows_for_aggregation, "accounts")

        if related_leads:
            record_data["leads"] = related_leads
        if related_contacts:
            record_data["contacts"] = related_contacts
        if related_accounts:
            record_data["accounts"] = related_accounts

    # if object is target item 
    # if object_name == "target_item":
    #     target_id = record_data.get("target_id")
    #     assigned_to = None
    #     if target_id:
    #         target_result = get_permissions(
    #             self.request,
    #             tableName="target",
    #             id=target_id,
    #             fields=["users_id"]
    #         ).get("data", [])
    #         if target_result:
    #             user_id = target_result[0].get("users_id")
    #             if user_id:
    #                 user_result = get_permissions(
    #                     self.request,
    #                     tableName="users",
    #                     id=user_id,
    #                     fields=["name"]
    #                 ).get("data", [])
    #                 if user_result:
    #                     assigned_to = user_result[0].get("name")
    #     record_data["assigned_to"] = assigned_to
    if object_name == "target_item":
        record_data = enrich_target_item_with_assigned_to(request, record_data, **kwargs)
    # --- Fetch related data ---
    related_data = {}
    for related in related_lists:
        related_model_name = related.get("object",{}).get("name", None)
        if not related_model_name:
            continue            
        foreign_key_field = related.get("related_field", {}).get("name", None)
        if not foreign_key_field:
            continue
        where = [{"field": foreign_key_field, "operator": "=", "value": record_id}]
        related_fields = related.get('fields', [])   
        fields = [field.get('name') for field in related_fields if field.get('visible')]   
        related_result = get_permissions(
            request,
            tableName=related_model_name,
            where=where,
            fields=fields,
            **kwargs
        )
        if str(related_model_name).lower() in ["event", "events"]:
            # Multi-select attendees/accounts are persisted as multiple event rows.
            # Collapse visually duplicate rows in related lists to one logical event.
            deduped_rows = []
            seen_keys = set()

            for row in related_result.get('data', []):
                dedupe_key = (
                    row.get('subject') or "",
                    row.get('start') or "",
                    row.get('end') or "",
                    row.get('owner_id') or "",
                    row.get('created_by_id') or "",
                )
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)
                deduped_rows.append(row)

            related_rows = deduped_rows
        else:
            related_rows = related_result.get('data', [])

        related_data[related_model_name] = {
            "related_list": related,
            "data": related_rows,
            "visible_columns": fields,
            "all_columns": related_result.get('all_columns', [])
        }

    # --- Fetch tasks and attachments ---
    tasks = get_permissions(
        request,
        tableName='task',
        fields = ['id', 'assigned_to_id', 'due_date', 'status', 'subject', 'related_to_object_id', 'assigned_to.name', 'created_date', 'last_modified_date'],
        where=[
            {"field": "related_to_object_id", "operator":"=", "value": record_id},
            {"field": "is_deleted", "operator": "=", "value": False},
        ],
        **kwargs
    ).get('data', [])
    
    attachments = get_permissions(
        request,
        tableName='file',
        where=[{"field": "record_id", "operator":"=", "value": record_id},
                {"field": "is_deleted", "operator": "=", "value": False}],
        **kwargs
    ).get('data', [])

    related_event_field_map = {
        "accounts": "accounts_id",
        "account": "accounts_id",
        "leads": "leads_id",
        "lead": "leads_id",
        "contact": "contacts_id",
        "contacts": "contacts_id",
    }
    related_event_field = related_event_field_map.get(str(object_name).lower())

    if related_event_field and record_id:
        events = get_permissions(
            request,
            tableName='event',
            where=[
                {"field": related_event_field, "operator": "=", "value": record_id},
                {"field": "is_deleted", "operator": "=", "value": False},
            ],
            **kwargs
        ).get('data', [])
    else:
        events = []

    if related_event_field and events and "event" not in related_data:
        event_visible_columns = ["name", "subject", "start", "end"]
        related_data["event"] = {
            "related_list": {
                "object": {"name": "event", "label": "Events"},
                "related_field": {"name": related_event_field},
                "fields": [
                    {"name": "name", "label": "Event ID", "visible": True},
                    {"name": "subject", "label": "Subject", "visible": True},
                    {"name": "start", "label": "Start", "visible": True},
                    {"name": "end", "label": "End", "visible": True},
                ],
            },
            "data": events,
            "visible_columns": event_visible_columns,
            "all_columns": [],
        }

    # #----Telephony config------
    telephone = get_permissions(
        request,
        tableName="telephony_config",
        where=[{"field":"target_object","operator":"=","value":object_details.get('id')}],
        **kwargs
    ).get("data",[])
    telephony = len(telephone) > 0
    if len(telephone) == 1:
        target_field = telephone[0].get("target_field",None)
        if target_field:
            ...

    # --- Fetch path builder ---
    path_builder_data = get_permissions(
        request,
        tableName='path_builder',
        where=[{"field": "object_id", "operator": "=", "value": object_details.get("id")}],
        **kwargs
    ).get("data", [])
    path_builder_data = path_builder_data[0] if path_builder_data else None

    # --- Fetch field history ---
    field_history_rows = get_field_history(object_name, record_id, schema=kwargs.get('schema', 'public'))
    history_data = [
        {
            "field_name": row[0],
            "old_value": row[1],
            "new_value": row[2],
            "changed_at": row[3],
        }
        for row in field_history_rows
    ]

    return {
        "object_metada": {
            'id': object_details.get('id'),
            'name': object_details.get('name'),
            'label': object_details.get('label'),
            'icon': object_details.get('icon'),
            'icon_color': object_details.get('icon_color'),
            "telephony":telephony
        },
        "data": {
            "id": record_data.get('id'),
            **record_data
        },
        "all_columns": all_columns,
        "layout": {
            **layout,
            "sections": sections,
            "buttons": buttons,
            "field_items": field_items,
            "related_lists": related_lists
        },
        "related_data": related_data,
        "tasks": tasks,
        "attachments": attachments,
        "path_builder": path_builder_data,
        "history": history_data,
        "events": events
    }
    