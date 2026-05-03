from api.permissions.permissions import get_permissions


def GetSearchLayouts(request, name, **kwargs):
    """
    Handles GET requests to retrieve search layouts for a specific object.
    """
    try:
        search_layouts = get_permissions(
            request,
            tableName='search_layouts',
            where=[{"field": "object.name", "operator": "eq", "value": name}],
            **kwargs
        ).get("data", [])
        fields = get_permissions(
            request,
            tableName='fields',
            where=[{"field": "object_name", "operator": "eq", "value": name}],
            fields=["id", "name", "label"],
            **kwargs
        ).get("data", [])
        return {
            "search_layout": search_layouts[0],
            "fields": fields
        }
    except Exception as e:
        raise Exception(f"Error retrieving search layouts: {str(e)}")