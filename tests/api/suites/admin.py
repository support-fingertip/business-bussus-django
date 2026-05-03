"""Admin suite — exercises /v2/admin/login + a basic admin GET. Skipped when
ADMIN_USERNAME / ADMIN_PASSWORD aren't configured."""
from __future__ import annotations


def run(client, ctx: dict, config) -> None:
    client.set_suite("Admin")

    if not (config.admin_username and config.admin_password):
        client.skip("admin login", "ADMIN_USERNAME / ADMIN_PASSWORD not set")
        return

    # Wrong password
    client.post("/v2/admin/login", json_body={
        "username": config.admin_username,
        "password": config.admin_password + "_wrong",
    }, anonymous=True)
    client.assert_status("admin login rejects wrong password", 401, 400)

    # Happy path
    client.post("/v2/admin/login", json_body={
        "username": config.admin_username,
        "password": config.admin_password,
    }, anonymous=True)
    res = client.assert_status("admin login succeeds", 200)
    if res.status != "pass":
        return
    client.assert_field("admin login returns access token", "access")

    admin_token = client.json_get("access")
    if not admin_token:
        return

    # Swap to admin token for an authenticated probe, restore afterwards
    saved = ctx.get("access_token")
    client.set_token(admin_token)
    try:
        # Generic admin route: /v2/admin/<table> — list users
        client.get("/v2/admin/users")
        client.assert_status("GET /v2/admin/users with admin token", 200, 403, 404)
    finally:
        client.set_token(saved)
