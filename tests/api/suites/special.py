"""Special routes — organization logo, invoice PDF, email/outlook auth URL."""
from __future__ import annotations


def run(client, ctx: dict, config) -> None:
    client.set_suite("Special routes")

    if not ctx.get("access_token"):
        client.skip("Special suite", "no auth")
        return

    client.get("/v2/api/organization/logo")
    # Logo route returns image bytes or a JSON pointer; accept any non-server-error.
    client.assert_status_in_range("GET /v2/api/organization/logo", 200, 404)

    # Outlook connect URL — does not require an existing account, just generates an OAuth URL.
    client.post("/v2/api/outlook/connect-url/", json_body={})
    client.assert_status_in_range("POST /v2/api/outlook/connect-url/", 200, 499)

    # Invoice PDF for a non-existent id — must NOT 500
    client.get("/v2/api/invoice/00000000-0000-0000-0000-000000000000/pdf")
    client.assert_status_in_range("GET /v2/api/invoice/<bogus>/pdf is a client error", 400, 499)
