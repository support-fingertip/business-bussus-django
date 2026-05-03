"""Setup / metadata suite — what the frontend loads when the user opens
the Setup section: profiles, custom objects, fields, page layouts.
These are read-only checks; we don't mutate metadata.
"""
from __future__ import annotations


def run(client, ctx: dict, config) -> None:
    client.set_suite("Setup metadata")

    if not ctx.get("access_token"):
        client.skip("Setup suite", "no auth")
        return

    client.get("/v2/api/setup/profiles")
    client.assert_status("GET /v2/api/setup/profiles", 200)

    client.get("/v2/api/setup/object")
    client.assert_status("GET /v2/api/setup/object", 200)

    # Pull fields for the configured object — needs an object id, fetch first.
    obj_name = config.crud_object
    object_id = None
    if isinstance(client.last_json, list):
        for row in client.last_json:
            if isinstance(row, dict) and row.get("name") == obj_name:
                object_id = row.get("id")
                break
    elif isinstance(client.last_json, dict):
        for key in ("data", "results"):
            arr = client.last_json.get(key)
            if isinstance(arr, list):
                for row in arr:
                    if row.get("name") == obj_name:
                        object_id = row.get("id")
                        break
            if object_id:
                break

    if object_id:
        client.get("/v2/api/setup/object/fields", params={"id": object_id})
        client.assert_status(f"GET /v2/api/setup/object/fields?id=<{obj_name}>", 200)
    else:
        client.skip("setup/object/fields", f"could not resolve object id for {obj_name!r}")

    client.get("/v2/api/setup/page_layouts")
    client.assert_status("GET /v2/api/setup/page_layouts", 200, 404)
