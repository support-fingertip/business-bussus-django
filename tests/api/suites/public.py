"""Public suite: unauthenticated routes — exists check, suggestions, OTP negative paths.

These all live under /v2/ without auth. We don't run the full signup OTP loop
because we can't read inboxes, but we verify the endpoints respond sanely.
"""
from __future__ import annotations


def run(client, ctx: dict, config) -> None:
    client.set_suite("Public (unauthenticated)")

    # exists check on the users table
    client.get("/v2/exists/users", params={"field": "email", "value": "no-such-user@example.invalid"},
               anonymous=True)
    client.assert_status("GET /v2/exists/users responds", 200, 400, 404)
    if client.last_status == 200:
        client.assert_field("exists response has 'exists' key", "exists")

    # exists check on the organizations table
    client.get("/v2/exists/organizations", params={"field": "domain", "value": "no-such-org-xyz"},
               anonymous=True)
    client.assert_status("GET /v2/exists/organizations responds", 200, 400, 404)

    # exists on an unknown table — must NOT 500
    client.get("/v2/exists/this_table_does_not_exist", params={"field": "x", "value": "y"},
               anonymous=True)
    client.assert_status_in_range("exists on unknown table doesn't 500", 400, 499)

    # username availability
    client.get("/v2/check/username/", params={"username": "no-such-user-xyz-zzz"}, anonymous=True)
    client.assert_status("GET /v2/check/username/", 200, 400)

    # domain suggestion
    client.get("/v2/suggestion/domain", params={"name": "Acme Co"}, anonymous=True)
    client.assert_status("GET /v2/suggestion/domain", 200, 400)

    # email suggestion
    client.get("/v2/suggestion/email", params={"name": "Jane Doe"}, anonymous=True)
    client.assert_status("GET /v2/suggestion/email", 200, 400)

    # OTP verify with garbage payload — never run real OTPs in CI
    client.post("/v2/verify", json_body={"verification_id": "fake", "otp": "000000"}, anonymous=True)
    client.assert_status_in_range("POST /v2/verify with bad data is a client error", 400, 499)
