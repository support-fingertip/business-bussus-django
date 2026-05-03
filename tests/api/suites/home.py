"""Home / dashboard suite — what the frontend loads on app boot."""
from __future__ import annotations


def run(client, ctx: dict, config) -> None:
    client.set_suite("Home / Dashboard")

    if not ctx.get("access_token"):
        client.skip("Home suite", "no auth")
        return

    client.get("/v2/api/home")
    client.assert_status("GET /v2/api/home", 200)

    client.get("/v2/api/notifications")
    # Notifications might be empty / unconfigured — accept any 2xx or 404.
    client.assert_status("GET /v2/api/notifications", 200, 204, 404)

    client.get("/v2/api/task")
    client.assert_status("GET /v2/api/task", 200, 404)

    # Field mapping is what the frontend uses to know columns/labels for an object.
    client.get("/v2/api/field_mapping", params={"object_name": config.crud_object})
    client.assert_status("GET /v2/api/field_mapping", 200, 404)
