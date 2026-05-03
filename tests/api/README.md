# API smoke-test runner

End-to-end test runner that drives the Bussus backend through the same
endpoints the frontend uses: login, list views, record reads/edits, user
creation, setup metadata, reports, and the public/auth surface.

Use it after every backend change to confirm nothing has regressed before
merging the branch upstream.

## Layout

```
tests/api/
├── run_tests.py           # entry point
├── config.py              # config loader (file + env + CLI)
├── client.py              # HTTP client + assertion helpers
├── config.example.json    # copy to config.json and fill in
├── requirements.txt
└── suites/
    ├── auth.py        # login (good/bad), token shape, /users/me, anon rejection
    ├── public.py      # /exists, /suggestion, /check/username, /verify (negative)
    ├── users.py       # list users, /users/me, create+update+delete a user
    ├── listview.py    # listview metadata, search_layouts, global_search, lookup
    ├── home.py        # home, notifications, task, field_mapping
    ├── crud.py        # full lifecycle on a configurable object
    ├── setup.py       # profiles, objects, fields, page_layouts (read-only)
    ├── reports.py     # list reports + fetch first
    ├── admin.py       # /v2/admin/login + /v2/admin/users (when configured)
    └── special.py     # organization/logo, outlook connect URL, invoice PDF
```

## Quickstart

```bash
cd tests/api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp config.example.json config.json
# edit config.json — at minimum set base_url, test_username, test_password

python run_tests.py
```

Exit status is non-zero when any assertion fails, so it works as-is in CI.

## Configuration

Three sources, highest priority wins:
1. CLI flags (`--base-url`, `--username`, `--password`, `--suite`, …)
2. Environment variables (`BASE_URL`, `TEST_USERNAME`, `TEST_PASSWORD`, `SUITES`, …)
3. `config.json`

Key fields:

| Field | Purpose |
|---|---|
| `base_url` | Where the backend is running (`http://localhost:8000` for `manage.py runserver`) |
| `test_username` / `test_password` | An existing user — the suites log in as this account |
| `admin_username` / `admin_password` | Optional; enables the admin suite |
| `new_user_profile_id` | Profile id used when creating a test user (find via `GET /v2/api/setup/profiles`) |
| `crud_object` | Which business object the CRUD lifecycle exercises (default `task`) |
| `crud_create_payload` / `crud_update_payload` | Bodies for POST/PATCH on that object |
| `suites` | List of suites to run, or `["all"]` |
| `keep_created` | Skip cleanup so you can inspect created records afterwards |
| `report_json` | Write a machine-readable report to this path |

## Examples

```bash
# run everything against a remote env
python run_tests.py --base-url https://qa.bussus.com --username qa@example.com --password ...

# only the auth and users suites, with per-request logging
python run_tests.py --suite auth,users --verbose

# stop on the first failure (fast feedback during development)
python run_tests.py --stop-on-failure

# emit a JSON report (useful for CI dashboards)
python run_tests.py --report-json artifacts/api-report.json

# list available suites
python run_tests.py --list-suites
```

## What gets tested

For each module the runner mirrors the user-visible UI flow:

- **Login page** — wrong password is rejected, empty payload is rejected,
  valid creds return `access` / `refresh` / `user`, JWT is accepted by
  `/users/me`, anonymous and tampered tokens are rejected.
- **App boot** — `/home`, `/notifications`, `/task`, `/field_mapping`.
- **List view page** — `/listview`, `/search_layouts`, `/global_search`, `/lookup`.
- **Record detail / edit** — full CRUD on the configured object: list →
  create → read → update → verify → delete.
- **Setup section** — profiles, objects, fields-of-object, page layouts.
- **Users management** — list users, get-one, `/users/me`, optionally
  create + update + delete a test user via `/setup/users`.
- **Reports** — list and fetch the first report.
- **Admin** — `/v2/admin/login` (when admin creds are provided) and a
  generic admin GET.
- **Special routes** — organization logo, Outlook OAuth URL, invoice PDF.
- **Public surface** — `/exists`, `/suggestion/domain`, `/suggestion/email`,
  `/check/username`, `/verify` with bad data.

## Output

```
Bussus API smoke-test runner
  base_url: http://localhost:8000
  user:     admin@example.com
  log:      .../logs/api_test_20260503-120403.log
  suites:   public, auth, users, listview, home, setup, reports, crud, admin, special

== Auth ==
  PASS login rejects wrong password [401 · 142ms]
  PASS login rejects empty payload [400 · 18ms]
  PASS login succeeds with valid creds [200 · 234ms]
  PASS login response carries access token [200 · 234ms]
  …

===== Test Summary =====
  total:   54
  passed:  52
  failed:  1
  skipped: 1
  duration: 12.4s

Failures:
  - [CRUD lifecycle on 'task'] PATCH /v2/api/task (update)
      PATCH /v2/api/task  →  expected [200, 201], got 500
```

A full request/response log is written to `logs/api_test_<timestamp>.log`
for post-mortem.

## Adding a new suite

1. Drop a `suites/<name>.py` exposing `def run(client, ctx, config): ...`.
2. Register it in `suites/__init__.py` (`REGISTRY` + `ORDERED_SUITES`).
3. The shared `ctx` dict carries state — `auth.py` populates `access_token`,
   `user_id`, `org_domain`, `profile_id` for downstream suites.

## Notes / gotchas

- The runner expects the backend to be reachable. For local dev: `python
  manage.py runserver` from the repo root, then point `base_url` at
  `http://localhost:8000`.
- Some objects require fields the default payload doesn't have. Override
  `crud_create_payload` for your tenant (look at what the frontend POSTs).
- Tests that need data the environment doesn't have (no profiles, no admin
  creds) skip rather than fail.
- The CRUD suite always cleans up after itself unless `keep_created` is on.
