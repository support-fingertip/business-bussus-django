# Session Handoff — security audit + Django ORM adoption

This document is a **self-contained brief** for a fresh Claude Code session
that picks up this work after the repo move from
`support-fingertip/bussus-bussiness-backend` to
`support-fingertip/business-bussus-django`. Read it first; it summarises
~3 hours of prior discussion and points at the artefacts that already
exist on disk.

---

## 1. What the original session did

The user asked for an exhaustive security + architecture audit of every
file under these folders:

```
api/APIs, api/BL/{dashboards,home,Listviews,ObjectManager,PageBuilder,
PageLayouts,PreviewPage,Profiles,Reports,Users,whatsapp},
api/emailsend/{utils}, api/formulas, api/migrations, api/notifications,
api/ORM/{AuditLogs,setup/{ObjectManager,utils,workflows},
sqlFunctions/{utils}}, api/pdfgen, api/permissions/{FetchUsers},
api/telephony, api/workflows
```

Five parallel `Explore` agents read every `.py` (~95 files / ~27,000 LOC)
and produced a file-by-file report. That report is **`SECURITY_AUDIT_REPORT.md`**
on branch `claude/security-audit-review-Es6C3` in the old repo.

Severity tally: **~32 CRITICAL, ~70 HIGH, ~55 MEDIUM, ~25 LOW.**

After the audit the user asked: *"do I need Django models for setup
objects and raw SQL for business objects, and is the architecture OK?"*

The answer was **yes** — split the data layer:

* **Setup / metadata tables** (fixed schema: profile, object, fields,
  page_layouts, sharing_records, workflow, …) → Django ORM models.
* **Business / dynamic objects** (Lead, Account, custom user-created
  tables) → keep raw SQL but wrap every identifier in
  `psycopg2.sql.Identifier`.

The macro architecture (DRF + JWT + schema-per-tenant + dynamic objects)
is sound — it's the implementation discipline that's broken.

---

## 2. What's already on disk (in this branch)

Branch `claude/phase1-django-orm-setup-models` ships **Phase 1**:

### New files

| File | Purpose |
|------|---------|
| `api/setup_models.py` | 47 Django models (`managed=False`) for every per-tenant setup table |
| `utils/tenant_schema.py` | `validate_schema`, `set_search_path`, `resolve_request_schema(request)` — schema **only** comes from JWT-resolved `Organization`. Never from headers/kwargs. |
| `utils/safe_sql.py` | `validate_identifier`, `validate_operator`, `qualified_table`, `column_exists`, `table_exists`, `list_tables_with_column`, `in_clause` — for the dynamic-object SQL paths that can't be modelled |
| `api/tenant_middleware.py` | `TenantSchemaMiddleware` — sets search_path per request, resets after. Wired into `version2/settings.py`. |

### Refactored files (all f-string SQL injection sites closed)

```
api/BL/recycle_bin.py
api/ORM/AuditLogs/audit_trail_logs.py
api/ORM/setup/ObjectManager/{delete_object,delete_field,post_object}.py
api/ORM/setup/newprofile.py
api/ORM/sqlFunctions/relationships.py
api/permissions/FetchUsers/{fetch_shared_records,fetch_all_subordinates}.py
api/workflows/workflow_executor.py
public/auth/login.py
utils/usergroup_utils.py
version2/settings.py     (middleware registered)
```

Full mapping in **`PHASE1_MIGRATION.md`** at the repo root.

### Audit report

**`SECURITY_AUDIT_REPORT.md`** at the repo root — the comprehensive
file-by-file findings. ~600 lines, this is the source of truth for what
still needs to be fixed.

---

## 3. What is NOT done — Phase 0 punch list

User clarified after Phase 1 shipped that Phase 0 should have come
first. Phase 0 is the **production blocker** set: items that must land
before any cut to prod, regardless of the Phase 1 ORM work.

About 60% of Phase 0 already shipped under the Phase 1 banner (the
TenantSchemaMiddleware, schema validator, identifier whitelist, every
f-string SQL fix, structured audit logging). The remaining items are:

### P0-1 — Re-enable IsAuthenticated and remove backdoor
* `api/APIs/dispatcher.py:13` — uncomment `permission_classes = [IsAuthenticated]`.
* `api/BL/blcontroller.py:~2602` — delete the `test_trigger` branch that
  hardcodes `'Ic2di7G72HEviqQpWV'` and calls `create_app(...)`.

### P0-2 — Rotate Voxbay credentials
* `api/telephony/views.py:311–317, 351` — `UID="rr809pi0j8"`,
  `PIN="561t2fuvd8"`, `EXT="108"`, `CALLER_ID="914847172533"` are
  hardcoded **in source** and shipped over **plain HTTP** in the URL.
* Rotate immediately, move to env vars, audit git history.

### P0-3 — Field-level write enforcement
* `api/permissions/permissions.py` `patch_permission` (~lines 755–920):
  filter `update_data` to `permitted_fields` (already returned by
  `get_field_metadata`) **before** calling `updateRawSQL`.
* Add an explicit deny-list for the `users` table:
  `profile_id`, `is_admin`, `is_superuser`, `is_staff`, `is_active`,
  `organization_id`. Without this, any user can self-promote via
  `PATCH /api/users/{me}` with `{"profile_id": "admin"}`.
* `api/permissions/permissions.py` `check_permission` (~476–494):
  derive `profile_id` from `request.user_.profile_id`, never from
  `kwargs`. Today any caller threading `request.data.profile_id`
  escalates trivially.

### P0-4 — Encrypt OAuth refresh tokens at rest
* `api/emailsend/utils/gmail_auth.py:82–86, 209–218` — refresh tokens
  stored as raw JSON in `email_provider_setup.cred`.
* `api/emailsend/utils/outlook_auth.py:94–96, 140–152` — refresh tokens
  in JSON file on disk **and** plaintext DB column.
* `api/emailsend/utils/nylas_service.py:40–41` — `grand_id` (sic)
  plaintext.
* Add Fernet encryption with key from env. Key should be stable across
  restarts, so `Fernet.generate_key()` at module load (see P0-7) is
  banned.

### P0-5 — Stop leaking exception text to clients
* `api/APIs/dispatcher.py:75–76, 108–109, 132–133, 154–155` — every
  HTTP verb has `except Exception as e: return Response({"message":
  str(e)}, status=500)`. Replace with `logger.exception(...)` +
  generic 500.

### P0-6 — HMAC verification on telephony CDR webhook
* `api/telephony/views.py:613–713` — `telephony_cdr` is `@csrf_exempt`,
  no auth, no signature check. Anyone can post forged CDRs and
  overwrite `recording_link` with a malicious URL.
* Implement HMAC-SHA256 with a shared secret in env; reject if signature
  header is missing or wrong.

### P0-7 — Kill broken module-load encryption
* `api/BL/utils.py:12–13` — `key = Fernet.generate_key()` at module
  import. Regenerated on every process restart, so previously
  encrypted data becomes undecryptable. Replace with key from env;
  fail-fast on `None`.
* `api/telephony/views.py:825` — same anti-pattern. Encryption wrapper
  is non-functional today.
* `api/BL/utils.py:125–134` — `encryptPassword` uses AES-CBC with a
  **fixed IV** from env. Same plaintext → same ciphertext. Replace with
  AES-GCM and random nonce per encryption.

### P0-8 — Workflow privilege inheritance
* `api/workflows/workflow_executor.py:~226, 366–368` — workflow
  create/update actions run with the caller's privileges, with no
  re-check that the caller can write the target object. A
  user-creatable workflow → privilege escalation.
* `api/workflows/create_records.py:89` and `api/workflows/update_records.py:75–90`
  — add target-object permission check before `post_data_sql` /
  `updateRawSQL`.

### P0-9 — xhtml2pdf XXE/SSRF
* `api/pdfgen/views.py:248` — `pisa.CreatePDF` is known-vulnerable to
  XXE via DOCTYPE entities and SSRF via `<img src="…">`. Replace with
  WeasyPrint configured with no-network URL fetcher, or sanitise input
  through `bleach` and disable external resource loading.
* `api/pdfgen/views.py:262` — InvoicePDFView only checks JWT, not
  record-level access. Any authenticated user with a guessed invoice
  id gets the PDF. Add `can_read_record` check.

### P0-10 — Recycle-bin authorization
* `api/BL/recycle_bin.py` — the table-name injection is fixed in
  Phase 1, but **no authz check** has been added. `permanently_delete_records`
  and `empty_recycle_bin` will hard-delete any record the request can
  name. Add per-record ownership / admin gate.

---

## 4. Suggested branch order on the new repo

```
main
 └─ phase1-django-orm-setup-models      # already shipped, port from old repo
 └─ phase0-security-fixes               # NEW — items P0-1 through P0-10
 └─ phase0-security-fixes  →  merge to main first
 └─ phase1-django-orm-setup-models  →  rebase on main, then merge
```

Phase 0 must merge first because P0-3 (field-write enforcement) and
P0-1 (re-enable IsAuthenticated) are independently exploitable today
and the Phase 1 ORM work doesn't help them.

---

## 5. Porting the existing branches

In a fresh checkout of the new repo:

```bash
git remote add old https://github.com/support-fingertip/bussus-bussiness-backend.git
git fetch old claude/phase1-django-orm-setup-models claude/security-audit-review-Es6C3

# Phase 1 work
git checkout -b phase1-django-orm-setup-models old/claude/phase1-django-orm-setup-models
git push -u origin phase1-django-orm-setup-models

# Audit report (file lives at repo root)
git checkout -b audit-report old/claude/security-audit-review-Es6C3
git push -u origin audit-report
```

After porting, this `HANDOFF.md`, `SECURITY_AUDIT_REPORT.md` and
`PHASE1_MIGRATION.md` will all be on the `phase1-django-orm-setup-models`
branch in the new repo.

---

## 6. First prompt for the new Claude session

Paste this verbatim:

> You are picking up a security-audit + ORM-adoption project. Read
> `HANDOFF.md`, `SECURITY_AUDIT_REPORT.md`, and `PHASE1_MIGRATION.md`
> at the repo root before doing anything else. Then create a new
> branch `claude/phase0-security-fixes` from `main` and address the
> P0-1 through P0-10 items in section 3 of `HANDOFF.md`. Use the
> Phase 1 helpers already shipped (`utils/tenant_schema.py`,
> `utils/safe_sql.py`, `api/tenant_middleware.py`,
> `api/setup_models.py`) wherever they fit. Commit each P0 item as a
> separate commit with the P0-N number in the message. Do NOT
> push until I review the diff.

---

## 7. Quirks / known issues

* **Python 3.12 syntax in `public/auth/login.py:137`** — pre-existing
  before this work; an f-string with nested double quotes that only
  parses on 3.12+. If your CI is on 3.11, this needs a separate fix
  (replace inner `"%H:%M %p"` with `'%H:%M %p'`). Out of scope for the
  audit / Phase 1.
* **`get_dashboards_from_reports.py` is 0 bytes** at
  `api/BL/dashboards/`. Dead file; can be removed.
* **`celerybeat-schedule`** binary file is checked in at the repo root.
  Should be in `.gitignore`.
* **Two `email_templates` CREATE TABLE statements** in
  `default_tables.sql` (lines ~762 and ~970). Postgres accepts only
  the first because of `IF NOT EXISTS`. The Phase 1 model
  (`api.setup_models.EmailTemplate`) merges the union of both column
  sets — verify against your live schema before relying on a column
  that only exists in the second definition.
* **`profile` table CREATE statement** is in
  `sqlfiles/setup_fields.sql`, not in `default_tables.sql`. Phase 1
  ships a Django model for it via observation of usage (only the
  fields actually read/written are mapped).
* **GitHub MCP scope** — each Claude session is locked to a single
  repo. The previous session was bound to
  `bussus-bussiness-backend`; the new session will be bound to
  `business-bussus-django` and won't be able to see the old repo's
  PRs or issues from inside Claude. The git CLI still works for
  `git fetch old` cross-remote operations.

---

## 8. Pointers into the audit findings (most exploitable first)

When the new session reads `SECURITY_AUDIT_REPORT.md`, these are the
findings to prioritise — the rest are secondary:

1. `api/permissions/permissions.py` — CVE-1, CVE-2, CVE-3 (profile_id
   from kwargs; sharing escalation; field-write missing).
2. `api/BL/Profiles/patch_profiles.py` — profile self-promotion via
   `PATCH /users/{me}`.
3. `api/BL/blcontroller.py:~2602` — `test_trigger` backdoor.
4. `api/telephony/views.py:311–317` — Voxbay creds in source.
5. `api/emailsend/*` — plaintext OAuth refresh tokens.
6. `api/pdfgen/views.py:248` — xhtml2pdf XXE/SSRF.
7. `api/workflows/workflow_executor.py:~226` — privilege inheritance.

These are independently exploitable today. Everything else is
defence-in-depth.

---

End of handoff.
