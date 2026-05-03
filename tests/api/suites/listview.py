"""List view suite — verifies the listview / search-layouts / global_search endpoints
that the frontend hits when the user opens any object's listing page.
"""
from __future__ import annotations


def run(client, ctx: dict, config) -> None:
    client.set_suite("List view")

    if not ctx.get("access_token"):
        client.skip("Listview suite", "no auth")
        return

    # Listview metadata for the configured object
    obj = config.crud_object
    client.get("/v2/api/listview", params={"object_name": obj})
    client.assert_status(f"GET /v2/api/listview?object_name={obj}", 200)

    # Search layouts ("recently viewed" sidebar uses these)
    client.get("/v2/api/search_layouts")
    client.assert_status("GET /v2/api/search_layouts", 200, 404)

    # Global search smoke — empty query should not 500
    client.get("/v2/api/global_search", params={"q": "test"})
    client.assert_status_in_range("GET /v2/api/global_search responds", 200, 499)

    # Lookup field smoke
    client.get("/v2/api/lookup", params={"object_name": obj, "field": "id", "limit": 5})
    client.assert_status_in_range("GET /v2/api/lookup responds", 200, 499)
