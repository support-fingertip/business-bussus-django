"""Auth suite: login (positive + negative), token shape, /users/me, anonymous rejection.

Side-effects: on a successful login, populates ctx with:
  ctx['access_token']  — JWT
  ctx['refresh_token'] — refresh token
  ctx['user_id']       — logged-in user id
  ctx['org_domain']    — organisation domain (used by some routes)
  ctx['profile_id']    — profile id from the login response
"""
from __future__ import annotations


def run(client, ctx: dict, config) -> None:
    client.set_suite("Auth")

    if not config.test_username or not config.test_password:
        client.skip("login (configured)", "TEST_USERNAME / TEST_PASSWORD not set")
        return

    # 1. Wrong password -> 401
    client.post("/v2/login", json_body={
        "username": config.test_username,
        "password": config.test_password + "_definitely_wrong",
    }, anonymous=True)
    client.assert_status("login rejects wrong password", 401, 400)

    # 2. Empty payload -> 400
    client.post("/v2/login", json_body={}, anonymous=True)
    client.assert_status("login rejects empty payload", 400, 401)

    # 3. Happy path
    client.post("/v2/login", json_body={
        "username": config.test_username,
        "password": config.test_password,
    }, anonymous=True)
    res = client.assert_status("login succeeds with valid creds", 200)
    if res.status != "pass":
        # Without a token nothing else will work — bail loudly so users see why.
        client.skip("further authenticated suites", "login failed")
        return

    client.assert_field("login response carries access token",  "access")
    client.assert_field("login response carries refresh token", "refresh")
    client.assert_field("login response carries user object",   "user")
    client.assert_field("login response carries user.id",       "user.id")
    client.assert_field_type("user.id is a string-ish value", "user.id", (str, int))

    access  = client.json_get("access")
    refresh = client.json_get("refresh")
    if not access:
        return

    ctx["access_token"]  = access
    ctx["refresh_token"] = refresh
    ctx["user_id"]       = client.json_get("user.id")
    ctx["org_domain"]    = client.json_get("user.domain")
    ctx["profile_id"]    = client.json_get("user.profile_id")
    client.set_token(access)

    # 4. Authenticated /users/me
    client.get("/v2/api/users/me")
    client.assert_status("GET /users/me with valid token", 200)
    client.assert_field("/users/me returns id",    "id")
    client.assert_field("/users/me returns email", "email")

    # 5. Anonymous /users/me must be rejected
    client.set_token(None)
    client.get("/v2/api/users/me", anonymous=True)
    client.assert_status("GET /users/me without token is rejected", 401, 403)
    client.set_token(access)

    # 6. Bogus token must be rejected
    client.set_token("not.a.valid.jwt")
    client.get("/v2/api/users/me")
    client.assert_status("GET /users/me with bogus token is rejected", 401, 403)
    client.set_token(access)
