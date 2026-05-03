def _strip_owner_id_filters(filters):
    """Remove owner_id conditions from filters since access group already handles ownership."""
    if isinstance(filters, list):
        return [f for f in filters if not (isinstance(f, dict) and f.get("field") == "owner_id")]
    if isinstance(filters, dict):
        if filters.get("field") == "owner_id":
            return None
        if "and" in filters:
            cleaned = _strip_owner_id_filters(filters["and"])
            return {"and": cleaned} if cleaned else None
        if "or" in filters:
            cleaned = _strip_owner_id_filters(filters["or"])
            return {"or": cleaned} if cleaned else None
    return filters


def add_private_owner_filter(filters, ids, shared_recs=None, assigned_to_field=None, assigned_to_id=None):
    private_filter = {"field": "owner_id", "operator": "in", "value": ids or []}

    or_conditions = [private_filter]
    if shared_recs:
        shared_ids = [r.get("record_id") for r in shared_recs if r.get("record_id")]
        if shared_ids:
            or_conditions.append({"field": "id", "operator": "in", "value": shared_ids})
    if assigned_to_field and assigned_to_id:
        or_conditions.append({"field": assigned_to_field, "operator": "=", "value": assigned_to_id})
    access_group = {"or": or_conditions}
    cleaned_filters = _strip_owner_id_filters(filters)
    if not cleaned_filters:
        return {"and": [access_group]}
    if isinstance(cleaned_filters, list):
        return {"and": [access_group, {"and": cleaned_filters}]}
    if isinstance(cleaned_filters, dict):
        return {"and": [access_group, cleaned_filters]}
    return {"and": [access_group]}
