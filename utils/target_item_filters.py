from api.permissions.permissions import get_permissions


def enrich_target_item_with_assigned_to(request, target_items, **kwargs):
    """
    Accepts a dict (single record) or list of dicts (multiple records).
    Adds 'assigned_to' (user name) to each target_item based on target_id.
    """
    # Handle single record
    if isinstance(target_items, dict):
        items = [target_items]
    else:
        items = target_items

    # Collect all unique target_ids
    target_ids = set(item.get("target_id") for item in items if item.get("target_id"))
    target_map = {}
    user_ids = set()

    # Fetch all targets in one go
    if target_ids:
        targets = get_permissions(
            request,
            tableName="target",
            where=[{"field": "id", "operator": "in", "value": list(target_ids)}],
            fields=["id", "users_id"],
            **kwargs

        ).get("data", [])
        for t in targets:
            target_map[t["id"]] = t.get("users_id")
            if t.get("users_id"):
                user_ids.add(t["users_id"])

    # Fetch all users in one go
    user_map = {}
    if user_ids:
        users = get_permissions(
            request,
            tableName="users",
            where=[{"field": "id", "operator": "in", "value": list(user_ids)}],
            fields=["id", "name"],
            **kwargs
        ).get("data", [])
        for u in users:
            user_map[u["id"]] = u.get("name")

    # Assign the user name to each target_item
    for item in items:
        assigned_to = None
        target_id = item.get("target_id")
        user_id = target_map.get(target_id)
        if user_id:
            assigned_to = user_map.get(user_id)
        item["assigned_to"] = assigned_to

    return target_items if isinstance(target_items, dict) else items