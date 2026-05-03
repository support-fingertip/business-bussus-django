"""Reports suite — list saved reports, fetch one, hit the report dispatcher endpoint.
Read-only; does not create/edit reports.
"""
from __future__ import annotations


def run(client, ctx: dict, config) -> None:
    client.set_suite("Reports")

    if not ctx.get("access_token"):
        client.skip("Reports suite", "no auth")
        return

    client.get("/v2/api/report")
    client.assert_status("GET /v2/api/report (list/index)", 200, 400, 404)

    # If we got back a list, try fetching the first report by id.
    first_id = None
    body = client.last_json
    if isinstance(body, list) and body:
        first_id = body[0].get("id") if isinstance(body[0], dict) else None
    elif isinstance(body, dict):
        for key in ("data", "results"):
            arr = body.get(key)
            if isinstance(arr, list) and arr and isinstance(arr[0], dict):
                first_id = arr[0].get("id")
                break

    if first_id:
        client.get("/v2/api/report", params={"id": first_id, "limit": 5})
        client.assert_status(f"GET /v2/api/report?id=<first>", 200, 400, 404)
    else:
        client.skip("fetch first report by id", "no reports listed")
