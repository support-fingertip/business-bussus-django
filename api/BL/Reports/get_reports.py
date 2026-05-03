from api.permissions.permissions import get_permissions
from api.BL.task import user_belongs_to_group

def get_reports(request, **kwargs):
    user_id = kwargs.get('user_', {}).get('id')
    profile_id = kwargs.get('user_', {}).get('profile_id')

    # Step 1: Get folders created by the current user
    my_folders = get_permissions(
                    request,
                    tableName='report_folder',
                    where=[
                        {"field": "is_deleted", "operator": "=", "value": False},
                        {"field": "created_by_id", "operator": "=", "value": user_id}
                    ],
                    **kwargs
                ).get('data', [])

    # Step 2: Get folders shared with the current user (by user_id or profile_id)
    shared_records = get_permissions(
        request,
        tableName="report_folder_sharing",
        where=[{
            "field": "shared_with_id",
            "operator": "in",
            "value": [user_id, profile_id]
        }],
        **kwargs
    ).get("data", [])

    shared_folder_ids = set()
    for rec in shared_records:
        if rec.get("shared_with_type") == "user" and rec.get("shared_with_id") == user_id:
            shared_folder_ids.add(rec.get("folder_id"))
        elif rec.get("shared_with_type") == "profile" and rec.get("shared_with_id") == profile_id:
            shared_folder_ids.add(rec.get("folder_id"))
        elif rec.get("shared_with_type") == "group":
            # If shared with a group, we need to check if the user belongs to that group
            group_id = rec.get("shared_with_id")
            if group_id and user_belongs_to_group(user_id, group_id, kwargs.get("schema", "public"), profile_id):
                shared_folder_ids.add(rec.get("folder_id"))
    shared_folders = []
    if shared_folder_ids:
        shared_folders = get_permissions(
            request,
            tableName='report_folder',
            where=[
                {"field": "is_deleted", "operator": "=", "value": False},
                {"field": "id", "operator": "in", "value": list(shared_folder_ids)}
            ],
            **kwargs
        ).get('data', [])

    # Combine: user's own folders + shared folders (deduplicated)
    my_folder_ids = {f['id'] for f in my_folders}
    folder_data = my_folders + [f for f in shared_folders if f['id'] not in my_folder_ids]

    # Return None if no folder data is found
    if not folder_data:
        return {"dashboards": None, "folders": None}

    # Step 2b: Get all subfolders of accessible folders (recursive)
    parent_folder_ids = [f['id'] for f in folder_data]
    collected_subfolder_ids = set(parent_folder_ids)

    def fetch_subfolders(parent_ids):
        """Recursively fetch subfolders for given parent folder IDs."""
        if not parent_ids:
            return []
        subfolders = get_permissions(
            request,
            tableName='report_folder',
            where=[
                {"field": "is_deleted", "operator": "=", "value": False},
                {"field": "parent_id", "operator": "in", "value": parent_ids}
            ],
            **kwargs
        ).get('data', [])
        # Filter out already collected folders to avoid cycles
        new_subfolders = [sf for sf in subfolders if sf['id'] not in collected_subfolder_ids]
        for sf in new_subfolders:
            collected_subfolder_ids.add(sf['id'])
        # Recurse into next level
        if new_subfolders:
            deeper = fetch_subfolders([sf['id'] for sf in new_subfolders])
            new_subfolders.extend(deeper)
        return new_subfolders

    subfolders = fetch_subfolders(parent_folder_ids)
    existing_ids = {f['id'] for f in folder_data}
    folder_data = folder_data + [sf for sf in subfolders if sf['id'] not in existing_ids]

    folder_name_map = {folder['id']: folder.get('name') for folder in folder_data}

    # Identify "Private Reports" and "Public Reports" folders
    private_folder_ids = [fid for fid, name in folder_name_map.items() if name == 'Private Reports']
    public_folder_ids = [fid for fid, name in folder_name_map.items() if name == 'Public Reports']

    # Step 3: Get all reports belonging to accessible folders
    all_accessible_folder_ids = [f['id'] for f in folder_data]
    all_reports = get_permissions(
        request,
        tableName='report',
        where=[
            {"field": "is_deleted", "operator": "=", "value": False},
            {"field": "folder_id", "operator": "in", "value": all_accessible_folder_ids}
        ],
        **kwargs
    ).get("data", [])

    # Step 3b: Get sharing records for all accessible folders
    all_sharing_records = get_permissions(
        request,
        tableName="report_folder_sharing",
        where=[
            {"field": "is_deleted", "operator": "=", "value": False},
            {"field": "folder_id", "operator": "in", "value": all_accessible_folder_ids}
        ],
        **kwargs
    ).get("data", [])

    # Build sharing map: folder_id -> list of sharing records
    sharing_map = {}
    for sr in all_sharing_records:
        fid = sr.get("folder_id")
        sharing_map.setdefault(fid, []).append(sr)

    # Build reports map: folder_id -> list of reports
    reports_map = {}
    for r in all_reports:
        fid = r.get("folder_id")
        reports_map.setdefault(fid, []).append(r)

    # Attach sharing records and reports to each folder
    for f in folder_data:
        f["sharing"] = sharing_map.get(f["id"], [])
        f["reports"] = reports_map.get(f["id"], [])

    # --- Enrich reports and folders with created_by / last_modified_by names ---
    user_ids = set()
    for r in all_reports:
        user_ids.add(r.get("created_by_id"))

    for f in folder_data:
        user_ids.add(f.get("created_by_id"))
        user_ids.add(f.get("last_modified_by_id"))

    if user_ids:
        user_ids = [uid for uid in user_ids if uid]

        user_map = {
            u["id"]: u["name"]
            for u in get_permissions(
                request, tableName="users", fields=["id", "name"],
                where=[{"field": "id", "operator": "in", "value": user_ids}],
                **kwargs
            ).get("data", [])
        }

        for r in all_reports:
            r["created_by"] = user_map.get(r.get("created_by_id"), "")

        for f in folder_data:
            f["created_by"] = user_map.get(f.get("created_by_id"), "")
            f["last_modified_by"] = user_map.get(f.get("last_modified_by_id"), "")

    # Step 4: Split reports based on folder
    private_reports = [r for r in all_reports if r.get('folder_id') in private_folder_ids]
    public_reports = [r for r in all_reports if r.get('folder_id') in public_folder_ids]

    # Step 5: Organize reports
    dashboards = {
        "recents": sorted(all_reports, key=lambda x: x.get("updated_at", ""), reverse=True)[:2],
        "created_by_me": [r for r in all_reports if r.get("created_by_id") == user_id],
        "all_reports": all_reports,
        "private_reports": private_reports,
        "public_reports": public_reports
    }

    # Step 6: Organize folders
    folders = {
        "created_by_me": my_folders,
        "all_folders": folder_data,
        "shared_with_me": shared_folders
    }

    return {
        "dashboards": dashboards,
        "folders": folders
    }
