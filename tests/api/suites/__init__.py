"""Test suites for the API smoke runner.

Each module exposes a single `run(client, ctx, config)` callable. `ctx` is a
mutable dict the suites share for cross-suite state (auth tokens, created
record ids, profile id, etc).
"""
from . import auth, public, users, listview, home, crud, setup, reports, admin, special

REGISTRY = {
    "auth":      auth.run,       # login (good/bad), /users/me, anon-rejection
    "public":    public.run,     # exists, suggestions, OTP start (negative)
    "users":     users.run,      # list users, get one, /users/me details
    "listview":  listview.run,   # list-view config + dynamic listview rows
    "home":      home.run,       # home/dashboard fetch
    "crud":      crud.run,       # create -> read -> list -> update -> delete on a configured object
    "setup":     setup.run,      # objects/profiles/fields metadata
    "reports":   reports.run,    # report list + simple fetch
    "admin":     admin.run,      # /v2/admin/login (when creds provided)
    "special":   special.run,    # organization/logo, smoke-test image
}

ORDERED_SUITES = [
    "public", "auth", "users", "listview", "home", "setup", "reports", "crud",
    "admin", "special",
]
