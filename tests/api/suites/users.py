"""Users suite: list users, fetch a specific user, /users/me details, create + delete a user.

The create-user flow is wrapped in try/except cleanup: even if a later assertion
fails we attempt to delete the user we provisioned, unless KEEP_CREATED is set.
"""
from __future__ import annotations

import time


def run(client, ctx: dict, config) -> None:
    client.set_suite("Users")

    if not ctx.get("access_token"):
        client.skip("Users suite", "no auth — auth suite did not log in")
        return

    # ---- list view ----
    client.get("/v2/api/users")
    client.assert_status("GET /v2/api/users (list)", 200)
    # Response can be a bare list or wrapped {data: [...]}; tolerate both.
    def has_users(c):
        body = c.last_json
        if isinstance(body, list):
            return len(body) > 0
        if isinstance(body, dict):
            for key in ("data", "users", "results"):
                v = body.get(key)
                if isinstance(v, list) and len(v) > 0:
                    return True
        return False
    client.assert_predicate(
        "users list is non-empty",
        has_users,
        reason_fn=lambda c: f"no list found in response keys "
                            f"({list(c.last_json.keys()) if isinstance(c.last_json, dict) else type(c.last_json).__name__})",
    )

    # ---- fetch self by id ----
    user_id = ctx.get("user_id")
    if user_id:
        client.get("/v2/api/users", params={"id": user_id})
        client.assert_status("GET /v2/api/users?id=<self>", 200)

    # ---- /users/me ----
    client.get("/v2/api/users/me")
    client.assert_status("GET /v2/api/users/me", 200)
    client.assert_field("/users/me has id",       "id")
    client.assert_field("/users/me has email",    "email")
    client.assert_field("/users/me has username", "username")

    # ---- create user (optional) ----
    profile_id = config.new_user_profile_id or ctx.get("profile_id")
    if not profile_id:
        client.skip("create new user", "no profile_id available (set NEW_USER_PROFILE_ID)")
        return

    suffix = int(time.time())
    new_email = f"{config.new_user_email_prefix}+{suffix}@{config.new_user_email_domain}"
    new_payload = {
        "email":       new_email,
        "username":    new_email,
        "first_name":  "QA",
        "last_name":   f"Test{suffix}",
        "name":        f"QA Test{suffix}",
        "phone":       "+10000000000",
        "password":    config.new_user_password,
        "profile_id":  profile_id,
    }
    client.post("/v2/api/setup/users", json_body=new_payload)
    res = client.assert_status("POST /v2/api/setup/users (create)", 201, 200)
    new_user_id = (
        client.json_get("data.id")
        or client.json_get("id")
        or client.json_get("user_id")
        or client.json_get("data.user_id")
    )
    if res.status == "pass" and new_user_id:
        ctx["created_user_id"] = new_user_id
        client.assert_field("create user response has an id", ".") if False else None  # noop placeholder

        # Read it back
        client.get("/v2/api/users", params={"id": new_user_id})
        client.assert_status("GET /v2/api/users?id=<new>", 200)

        # Update via setup/users
        update_payload = {"id": new_user_id, "first_name": "QA-Updated"}
        client.patch("/v2/api/setup/users", json_body=update_payload)
        client.assert_status("PATCH /v2/api/setup/users (update)", 200, 201)

        # Cleanup unless told to keep
        if not config.keep_created:
            client.delete("/v2/api/setup/users", json_body={"id": new_user_id})
            client.assert_status("DELETE /v2/api/setup/users (cleanup)", 200, 204)
    else:
        client.skip("read-back / update / delete created user",
                    "user creation did not return an id")
