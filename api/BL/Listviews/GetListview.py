from collections import defaultdict
from datetime import datetime, timedelta
from CacheService.cache import CacheService, DjangoCacheBackend
from api.BL.utils import construct_filters, process_filters
from api.permissions.permissions import get_permissions
from utils.filter_logic_parser import convert_to_query_format
from utils.access_level_filter import add_private_owner_filter
from api.permissions.FetchUsers.fetch_shared_records import fetch_shared_records
from utils.target_item_filters import enrich_target_item_with_assigned_to
from api.BL.computed_fields import process_computed_fields_for_report, apply_computed_fields_to_records, separate_computed_filters, apply_computed_filters
from django.db import connection
from pprint import pprint

cache = CacheService(DjangoCacheBackend(alias="default"))


def is_column_exist(schema_name, table_name, column_name):
    if not schema_name or not table_name or not column_name:
        return False
    with connection.cursor() as cursor:
        cursor.execute("SET search_path TO %s", [schema_name])
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
              AND column_name = %s
            LIMIT 1
            """,
            [schema_name, table_name, column_name],
        )
        return cursor.fetchone() is not None


def normalize_visible_columns(visible_columns, object_name, schema_name):
    safe_columns = list(visible_columns) if isinstance(visible_columns, list) else []

    if not safe_columns:
        if is_column_exist(schema_name, object_name, "name"):
            safe_columns.append("name")

    # if (
    #     is_column_exist(schema_name, object_name, "owner_id")
    #     and "owner_id" not in safe_columns
    # ):
    #     safe_columns.append("owner_id")

    # if (
    #     is_column_exist(schema_name, object_name, "created_date")
    #     and "created_date" not in safe_columns
    # ):
    #     safe_columns.append("created_date")

    return safe_columns


def append_and_filter(existing_filters, new_filter):
    """Append a filter with AND semantics while preserving existing filter shape."""
    if not existing_filters:
        return new_filter

    if isinstance(existing_filters, dict):
        if "and" in existing_filters:
            existing_filters["and"].append(new_filter)
            return existing_filters
        return {"and": [existing_filters, new_filter]}

    if isinstance(existing_filters, list):
        return {"and": existing_filters + [new_filter]}

    return {"and": [existing_filters, new_filter]}

USER_LOOKUP_FIELDS = ('created_by_id', 'owner_id', 'last_modified_by_id', 'users_id')


def resolve_user_ids_in_data(data_list, visible_columns, schema):
    """
    For any user lookup field (created_by_id, owner_id, last_modified_by_id) present
    in visible_columns, batch-fetch the corresponding user names and replace the raw
    ID values in each record with the human-readable name.
    """
    if not data_list or not schema:
        return data_list

    fields_to_resolve = [f for f in USER_LOOKUP_FIELDS if f in visible_columns]
    if not fields_to_resolve:
        return data_list

    # Collect all unique user IDs across all relevant fields
    user_ids = set()
    for record in data_list:
        for field in fields_to_resolve:
            val = record.get(field)
            if val:
                user_ids.add(val)

    if not user_ids:
        return data_list

    # Batch-fetch user names in a single query
    user_id_to_name = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO %s", [schema])
            placeholders = ','.join(['%s'] * len(user_ids))
            cursor.execute(
                f"SELECT id, name FROM users WHERE id IN ({placeholders})",
                list(user_ids),
            )
            for row in cursor.fetchall():
                user_id_to_name[row[0]] = row[1]
    except Exception:
        return data_list

    # Replace IDs with names in the records
    for record in data_list:
        for field in fields_to_resolve:
            val = record.get(field)
            if val and val in user_id_to_name:
                record[field] = user_id_to_name[val]

    return data_list


def GetListviews(request, **kwargs):
    another_object = kwargs.get('object_name')
    limit = request.GET.get('limit')
    offset = request.GET.get('offset')
    search_term = request.GET.get('search')    
    try:
        limit = int(limit) if limit is not None else 10  # Default limit
        offset = int(offset) if offset is not None else 0  # Default offset
    except ValueError:
        raise Exception({"error": "Invalid limit or offset. They must be integers."})

    # Special case: 'calendar' is a system table not registered in the object metadata table.
    # Bypass the normal listview mechanism and directly return all calendar records.
    if another_object == 'calendar':
        result = get_permissions(
            request,
            tableName='calendar',
            limit=limit,
            offset=offset,
            **kwargs
        )
        return result

    if not another_object:
        obj = request.GET.get('object')                                     
        if obj:
            # result = cache.get('all_listviews_'+obj, "listviews", kwargs.get('schema'))
            # if result is None:                
            #     where = [{'field': 'object.name', 'value': obj, 'operator': '='}]
            #     result = get_permissions(request, tableName='listviews', where = where, **kwargs ).get('data')
            #     cache.set('all_listviews_'+obj, result, "listviews", kwargs.get('schema')) # Cache for 5 minutes
            where = [{'field': 'object.name', 'value': obj, 'operator': '='}]
            # if obj == 'task':
            #     where.append({'field': 'assigned_to_id', 'value': kwargs.get('user_', {}).get('id'), 'operator': '='})
            result = get_permissions(request, tableName='listviews', where = where, **kwargs ).get('data')
            return result     
                        
    listview_name = request.GET.get('listview')
    
    # Handle pinning: if no listview is specified, look for pinned one
    if not listview_name:
        pinned_where = [
            {'field': 'object.name', 'value': another_object, 'operator': '='},
            {'field': 'is_pinned', 'value': True, 'operator': '='}
        ]
        pinned_result = get_permissions(request, tableName='listviews', where=pinned_where, **kwargs).get('data')
        if pinned_result:
            listview_name = pinned_result[0].get('name')
        else:
            listview_name = 'all'

    sort_by_field = request.GET.get('sort_by')
    is_asc = request.GET.get('is_asc')
    order_by=[]
    if sort_by_field:
        sort_direction = "ASC" if str(is_asc).lower() == "true" else "DESC"
        order_by = [{"field": sort_by_field, "direction": sort_direction}]
    else:
        if is_recently_viewed_column_exist(**kwargs):
            order_by = [{"field": 'recently_viewed', "direction": "DESC"}]         
    try: 
        object_details = get_permissions(request, tableName='object', where = [{'field': 'name', 'value': another_object, 'operator': '='}], **kwargs ).get('data')[0]
    except Exception:
        raise Exception('Object not found.')
    
    data = get_listview_for_object(listview_name, object_details=object_details, **kwargs)
    filters_ = data.get("filters", [])   
    if not isinstance(filters_, list):
        filters_ = [] 
    filter_logic = data.get('filter_logic')
    if filters_ and filter_logic and filter_logic.strip() != "":
        # Process filters for datatype enrichment
        processed_filters = process_filters(filters_, another_object, **kwargs)
        filter_logic = data.get('filter_logic')
        # Apply filter logic to create tree structure
        filters = convert_to_query_format(processed_filters, filter_logic)
    else:       
        filters = process_filters(filters_, another_object, **kwargs) if filters_ else None
    visible_columns = data.get("visible_columns") or ['name']
    visible_columns = normalize_visible_columns(
        visible_columns,
        another_object,
        kwargs.get("schema"),
    )

    required_fields_param = request.GET.get('required_fields', '')
    if required_fields_param:
        for field in required_fields_param.split(','):
            field = field.strip()
            if field and field not in visible_columns:
                visible_columns.append(field)

    search_filters = {}        
    if search_term:                
        search_filters = construct_filters(visible_columns, another_object, search_term, **kwargs)
    combined_filters = None
    if filters and search_filters:
        combined_filters = {
            "and": [filters, search_filters]
        }
    elif filters:
        combined_filters = filters
    else:
        combined_filters = search_filters

    # Always exclude soft-deleted records from module list views.
    is_deleted_filter = {'field': 'is_deleted', 'value': False, 'operator': '='}
    combined_filters = append_and_filter(combined_filters, is_deleted_filter)

    # Keep converted leads in DB, but hide them from Leads module listings.
    if another_object in ('lead', 'leads') and is_column_exist(kwargs.get('schema'), 'leads', 'is_converted'):
        converted_filter = {'field': 'is_converted', 'value': False, 'operator': '='}
        combined_filters = append_and_filter(combined_filters, converted_filter)

    # is_deleted_filter is already applied above via append_and_filter — no duplicate needed
        
    profile = get_permissions(request, tableName='profile', where=[{'field': 'id', 'value': kwargs.get('profile_id'), 'operator': '='}], **kwargs).get('data')[0]
    if profile.get('profile_type') != 'admin':
        user_id = kwargs.get('user_', {}).get('id')
        schema = kwargs.get('schema')
        if another_object == 'task':
            user_filter = {'field': 'assigned_to_id', 'value': user_id, 'operator': '='}
            if isinstance(combined_filters, dict) and 'and' in combined_filters:
                combined_filters['and'].append(user_filter)
            elif isinstance(combined_filters, dict) and 'or' in combined_filters:
                combined_filters = {
                    'and': [combined_filters, user_filter]
                }
            else:
                combined_filters = {
                    'and': [combined_filters, user_filter]
                }
        elif another_object in ('event', 'events'):
            shared_recs = fetch_shared_records(user_id, another_object, schema, type='read/write')
            combined_filters = add_private_owner_filter(
                combined_filters, [user_id], shared_recs,
                assigned_to_field='users_id', assigned_to_id=user_id
            )
        else:
            shared_recs = fetch_shared_records(user_id, another_object, schema, type='read/write')
            combined_filters = add_private_owner_filter(combined_filters, [user_id], shared_recs)
    if another_object == "task" and 'object_id' not in visible_columns:
        visible_columns.append('object_id')

    # Separate computed fields (formula/rollup) from physical fields
    schema = kwargs.get('schema', 'public')
    physical_columns, computed_fields, extra_deps = process_computed_fields_for_report(visible_columns, another_object, schema)
    for dep in extra_deps:
        if dep not in physical_columns:
            physical_columns.append(dep)

    # Separate computed filters from physical filters
    computed_field_names = {meta.get("name", k) for k, meta in computed_fields.items()} | set(computed_fields.keys())
    combined_filters, computed_filters_list = separate_computed_filters(combined_filters, computed_field_names, schema, another_object)

    result = get_permissions(request,
                                tableName=another_object,
                                fields = physical_columns,
                                where=combined_filters,
                                order_by=order_by,
                                limit=limit, offset=offset, **kwargs)
    # ✅ Pagination Logic
    data_list = result.get('data', [])

    # Compute formula/rollup values for list view records
    if computed_fields and data_list:
        data_list = apply_computed_fields_to_records(data_list, computed_fields, another_object, schema)
    if computed_filters_list and data_list:
        data_list = apply_computed_filters(data_list, computed_filters_list)

    if another_object == "task" and 'related_to_object_id' in visible_columns:
        data_list = enrich_task_with_related_to(request, result.get('data', []), **kwargs)
    if another_object == "target_item":
        data_list = enrich_target_item_with_assigned_to(request, data_list, **kwargs)
    data_list = resolve_user_ids_in_data(data_list, visible_columns, kwargs.get('schema'))
    # ✅ Calculate actual total count matching filters
    total_records_result = get_permissions(request, 
                                tableName=another_object,
                                fields = [{'name': 'id', 'aggregate': 'count', 'alias': 'total_count'}], 
                                where=combined_filters,  
                                report=True,
                                **kwargs)
    total_records = total_records_result.get('data', [{}])[0].get('total_count', 0) if total_records_result.get('data') else 0

    # hasmore = (offset + limit) < total_records
    hasmore = (offset + len(data_list)) < total_records
    filters = [{'field': 'object_id', 'value': object_details.get('id'), 'operator': '='},{'field': 'profile_id', 'value': kwargs.get('profile_id'), 'operator': '='}]
    permissions = get_permissions(request, tableName="object_permissions",where=filters, **kwargs)
    return {
        "object":{
            "id": object_details.get('id'),
            "name": object_details.get('name'),
            "label": object_details.get("label"),
            "plural_label": object_details.get('plural_label')                    
        },
        "listview": {                    
            "id": data.get('id'),
            "label": data.get('label'),
            "name": data.get('name')
        },
        "sort_by": order_by,
        "filter_logic": data.get('filter_logic'),
        "filters": filters_,
        "visible_columns": visible_columns,
        "hasmore":hasmore,
        **{**result, "data": data_list},  
        "metadata":{
            "total": total_records,
            "limit": limit,
            "offset": offset
        },
        "permissions": permissions.get('data', [])   
    }
    
def enrich_task_with_related_to(request, tasks_result, **kwargs):
    obj_and_ids_map = defaultdict(set)
    for task in tasks_result:
        object = task.get('object', {}).get('name')
        record_id = task.get('related_to_object_id')
        if object and record_id:
            obj_and_ids_map[object].add(record_id)
    related_records = []        
    for object, ids in obj_and_ids_map.items():
        x = get_permissions(
            request,
            tableName=object,
            fields=['id', 'name'],
            where=[{"field": "id", "operator": "in", "value": list(ids)}, {"field": "is_deleted", "operator": "=", "value": False}],
            **kwargs
        ).get('data', [])
        related_records.extend(x)
    related_map = {rec['id']: rec['name'] for rec in related_records}
    for task in tasks_result:
        if task.get('related_to_object_id') in related_map:
            task['related_to'] = {
                'id': task.get('related_to_object_id'),
                'name': related_map[task.get('related_to_object_id')]
            }    
    return tasks_result
        
    
    
def get_listview_for_object(listview_name=None, **kwargs):
    """
    Read-through cache:
      1) Try cache by (record_id=listview_name, table='listviews', schema)
      2) If miss -> query DB, set in cache, return
    """
    object_name = kwargs.get('object_name')
    schema = kwargs.get('schema')
    table = "listviews"

    # Sanity: make sure we have schema
    if not schema:
        raise ValueError("schema is required for caching")    

    # 1) Try cache first
    # cached = cache.get(listview_name, table, schema)
    # if cached is not None:
    #     return cached

    # 2) Cache miss -> query
    where = [{'field': 'object.name', 'value': object_name, 'operator': '='}]
    if listview_name:
        where.append({'field': 'name', 'value': listview_name, 'operator': '='})

    result = get_permissions(None, tableName='listviews', where=where, **kwargs).get('data')
    
    # 3) Handle dynamic listviews for ANY object if not found in DB
    if not result:
        dynamic_listview = get_dynamic_listview(listview_name, **kwargs)
        if dynamic_listview:
            return dynamic_listview

    if not result:
        raise Exception('Listview not found.')

    # 4) Store the first row (adjust as you like)
    #cache.set(listview_name, table=table, schema=schema, value=result[0], ttl=300)  # Cache for 5 minutes
    return result[0]

def get_dynamic_listview(listview_name, **kwargs):
    """
    Generate dynamic listview filters for date-based filtering on any object.
    """
    object_name = kwargs.get('object_name')
    object_details = kwargs.get('object_details')
    
    if not object_details:
        try:
            object_details = get_permissions(None, tableName='object', where=[{'field': 'name', 'value': object_name, 'operator': '='}], **kwargs).get('data')[0]
        except Exception:
            return None

    plural_label = object_details.get('plural_label', object_name.title())
    today = datetime.today().date()
    filters = []
    
    # Generic mapping of listview names to date filters
    date_filters = {
        "today": {
            "label": f"Today {plural_label}",
            "filters": [
                {"field": "created_date", "operator": ">=", "value": str(today)},
                {"field": "created_date", "operator": "<", "value": str(today + timedelta(days=1))}
            ]
        },
        "yesterday": {
            "label": f"Yesterday {plural_label}",
            "yesterday": today - timedelta(days=1),
            "filters": [
                {"field": "created_date", "operator": ">=", "value": str(today - timedelta(days=1))},
                {"field": "created_date", "operator": "<", "value": str(today)}
            ]
        },
        "this_week": {
            "label": f"This Week {plural_label}",
            "filters": [
                {"field": "created_date", "operator": ">=", "value": str(today - timedelta(days=today.weekday()))},
                {"field": "created_date", "operator": "<", "value": str(today + timedelta(days=1))}
            ]
        },
        "last_week": {
            "label": f"Last Week {plural_label}",
            "filters": [
                {"field": "created_date", "operator": ">=", "value": str(today - timedelta(days=today.weekday() + 7))},
                {"field": "created_date", "operator": "<", "value": str(today - timedelta(days=today.weekday()))}
            ]
        },
        "this_month": {
            "label": f"This Month {plural_label}",
            "filters": [
                {"field": "created_date", "operator": ">=", "value": str(today.replace(day=1))},
                {"field": "created_date", "operator": "<", "value": str(today + timedelta(days=1))}
            ]
        },
        "last_month": {
            "label": f"Last Month {plural_label}",
            "filters": [
                {"field": "created_date", "operator": ">=", "value": str((today.replace(day=1) - timedelta(days=1)).replace(day=1))},
                {"field": "created_date", "operator": "<=", "value": str(today.replace(day=1) - timedelta(days=1))}
            ]
        },
        "all": {
            "label": f"All {plural_label}",
            "filters": []
        }
    }

    # Handle object-specific "all" names like "all_leads"
    if listview_name == f"all_{object_name}":
        listview_name = "all"

    if listview_name not in date_filters:
        return None

    config = date_filters[listview_name]
    
    # Get "all" listview to use its visible columns as a default
    try:
        all_where = [{'field': 'object.name', 'value': object_name, 'operator': '='}, {'field': 'name', 'value': 'all', 'operator': '='}]
        all_listview = get_permissions(None, tableName='listviews', where=all_where, **kwargs).get('data')
        visible_columns = all_listview[0].get("visible_columns") if all_listview else ["name", "created_date"]
    except Exception:
        visible_columns = ["name", "created_date"]

    visible_columns = normalize_visible_columns(
        visible_columns,
        object_name,
        kwargs.get("schema"),
    )

    return {
        "id": listview_name,
        "name": listview_name,
        "label": config["label"],
        "filters": config["filters"],
        "visible_columns": visible_columns,
        "filter_logic": ""
    }


def is_recently_viewed_column_exist(**kwargs):
    schema_name = kwargs.get('schema')
    object_name = kwargs.get('object_name')
    if not schema_name or not object_name:
        raise ValueError("schema and object_name are required")

    with connection.cursor() as cursor:
        cursor.execute("SET search_path TO %s", [schema_name])
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
              AND column_name = 'recently_viewed'
        """, [schema_name, object_name])
        result = cursor.fetchone()
        return result is not None
    

def field_level_permissions(request,obj, all_columns, **kwargs): 
    try:
        for column in all_columns:
            field_filter = [{'field': 'object_name', 'value': obj, 'operator': '='}, 
            {'field': 'name', 'value': column.get("name"), 'operator': '='}]
            field = get_permissions(request, tableName='fields', where=field_filter, **kwargs).get('data',[None])[0]
            filters = [{'field': 'object_id', 'value': field.get("object_id"), 'operator': '='}, 
                       {'field': 'fields_id', 'value': field.get("id"), 'operator': '='},
                       {'field': 'profile_id', 'value': kwargs.get('profile_id'), 'operator': '='}]
            permissions = get_permissions(request, tableName='field_permissions', where=filters, **kwargs).get('data', [])
            column['permissions'] = permissions[0] if permissions else {}
        return all_columns
    except Exception as e:
        print("Error in field_level_permissions:", e)
        return all_columns



class ListView:
    def __init__(self, request, **kwargs):
        self.request = request
        self.kwargs = kwargs
    
    def get_component_data(self, component_type, chart_config, filtered_data):
        """
        Process and return data for different dashboard components based on their type and configuration.
        """
        try:
            component_data = {}
        # ✅ Process Metric Components
            if component_type == "metric":
                metric_config = chart_config.get("metric_config", {})
                if "count" in metric_config:
                    return len(filtered_data)
                if "sum" in metric_config:
                    field = metric_config["sum"]
                    values = [entry[field] for entry in filtered_data if field in entry and entry[field] is not None]
                    return sum(values) if values else 0
                if "average" in metric_config:
                    field = metric_config["average"]
                    values = [entry[field] for entry in filtered_data if field in entry and entry[field] is not None]
                    return sum(values) / len(values) if values else 0
            # ✅ Process Chart Components
            elif "chart" in component_type: 
                group_by_field = chart_config.get("group_by", "status")  # Default to status if not provided
                chart_data = defaultdict(int)
                for entry in filtered_data:
                    key = entry.get(group_by_field, "Unknown")
                    chart_data[key] += 1
                # Create the list of labels and values
                labels = list(chart_data.keys())  # List of unique values (labels)
                values = list(chart_data.values())  # List of counts (values)
                component_data = {
                    "labels": labels,
                    "values": values
                }   
                return component_data
            # ✅ Process Table Components
            elif component_type == "table":
                visible_columns = chart_config.get("visible_columns", ["id", "name"])  # Default columns if not provided
                component_data = [{col: entry.get(col, None) for col in visible_columns} for entry in filtered_data]
                return component_data
            return component_data
        except Exception as e:
            return len(filtered_data)   
        