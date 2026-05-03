from api.permissions.permissions import get_permissions

def get_field_mapping(request, object_id, **kwargs):
    """
    Retrieves field mappings for a given object ID.
    """
    try:
        kwargs.pop('id', None)
        field_mappings = get_permissions(
            request,
            tableName='field_mapping',
            where=[{"field": "object_id", "operator": "eq", "value": object_id}],
            fields = ['object_id', 'object.name', 'object.label', 'mapped_with.name', 'mapped_with.label', 'mapped_with.id', 'mapped_fields'],
            **kwargs
        ).get("data", [])
        return field_mappings
    except Exception as e:
        raise Exception(f"Error retrieving field mappings: {str(e)}")