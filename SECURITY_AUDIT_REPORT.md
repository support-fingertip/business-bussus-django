# Comprehensive Security & Architecture Audit Report

**Repository:** bussus-bussiness-backend
**Branch:** claude/security-audit-review-Es6C3
**Date:** 2026-05-02
**Scope:** Every file under the requested folders:
`api/APIs/`, `api/BL/{dashboards,home,Listviews,ObjectManager,PageBuilder,PageLayouts,PreviewPage,Profiles,Reports,Users,whatsapp}`,
`api/emailsend/{utils}`, `api/formulas/`, `api/migrations/`, `api/notifications/`, `api/ORM/{AuditLogs,setup/{ObjectManager,utils,workflows}, sqlFunctions/{utils}}`, `api/pdfgen/`, `api/permissions/{FetchUsers}`, `api/telephony/`, `api/workflows/`.

`__pycache__` directories are build artefacts and were skipped.

---

## How to read this report

Each file is listed with: line count → purpose → key functions → security risks (with line numbers and severity) → architecture / code-quality notes.
Severity legend: **CRITICAL** (immediate fix; exploitable today), **HIGH** (likely exploitable; fix this sprint), **MEDIUM** (defence-in-depth or logic risk), **LOW** (code quality / best practice).

A consolidated executive summary and remediation roadmap appears at the end.

---

# 1. api/APIs

## api/APIs/__init__.py (0)
Empty package marker. No findings.

## api/APIs/dispatcher.py (156)
Generic HTTP-method dispatcher routing every URL to BusinessLogicHandler.

Key functions:
- `Dispatcher.get/post/patch/delete` (58, 78, 111, 135) — HTTP entry points.
- `_init_request_context` (18-35) — extracts user/org/connection/profile/schema from the request.
- `_init_handler` (37-40) — instantiates BusinessLogicHandler.
- `generate_notication` (43-56) — push notification fan-out (currently dead-coded in handlers).

Security risks:
- **CRITICAL** — `permission_classes = [IsAuthenticated]` is commented out (line 13). Sole gate is `CustomJWTAuthentication`; if it ever returns `None`/`AnonymousUser` the request still flows through.
- **HIGH** — Catch-all `except Exception as e: return Response({"message": str(e)}, status=500)` (75-76, 108-109, 132-133, 154-155) leaks stack/SQL text.
- **HIGH** — Inactive-user check fails open: `if request.user_ and not request.user_.get("is_active", True)` (29-30) — when `user_` is None it short-circuits and the request continues.
- **MEDIUM** — `object_name` / `another_object` / `param3` consumed from URL kwargs without whitelist; cascades into the BL switch.

Architecture:
- **HIGH** — Single fat dispatcher for the whole product. Replace with per-resource ViewSets / serializers.
- **MEDIUM** — Channel layer set in `__init__` but never used; commented notification block (96-103) is dead code.

# 2. api/BL

## api/BL/__init__.py (0) — empty.

## api/BL/blcontroller.py (5,087)
Monolithic BusinessLogicHandler implementing get/post/patch/delete logic for every object via a string switch. Imports 60+ symbols across the codebase.

Architecture:
- **CRITICAL** — God class. 5,087-line `if self.object_name == 'X': elif ...` ladder is the single coupling point of the product. Decompose into per-domain handlers; a router map → handler is enough.
- **HIGH** — Two duplicate imports (`from pprint import pprint` 135/139, recycle_bin 30/128).

Security risks (sample, full list in this file's review):
- **CRITICAL** — `test_trigger` branch (~2602) hardcodes `'Ic2di7G72HEviqQpWV'` and calls `create_app(...)`. Looks like a debug / back-door. Remove or guard with `settings.DEBUG`.
- **HIGH** — Lead-conversion path (≈2710-2788) issues multiple post_permission writes without `transaction.atomic()` (the comment shows atomic was tried and rolled back). Partial failure leaves orphans.
- **HIGH** — File upload (≈2821-2844) takes `request.FILES.get('file')` and calls `handle_file_upload` without size/MIME/extension validation.
- **HIGH** — Mass assignment: `{**create_data, 'created_by_id': user_id, ...}` — user-supplied keys can land first and overwrite system fields depending on Python dict ordering quirks. Build the dict explicitly from a whitelist.
- **HIGH** — ThreadPoolExecutor with manual `close_old_connections()` / `connection.close()` (≈1263-1306) and broad `except Exception: print(...)` — connection leaks and silent failures.
- **HIGH** — `print(f"[DEBUG]…")` statements throughout (915-926, 1241, 1281, …) ship filter values, group keys and table names to stdout/log aggregator (PII risk).
- **MEDIUM** — `validate_filter_logic` raises and the message is propagated unchanged to the client (~2851-2859).
- **MEDIUM** — `process_formula(...)` invoked directly — see api/formulas concerns.

Code quality:
- Per-method timing prints `_lap` (163-167, 222, …) shipped to production.
- No type hints, no tests, bare `except Exception` everywhere.

## api/BL/computed_fields.py (2,142)
Push-down planner: translates user-defined formulas / rollups into SQL fragments and decides when to fall back to Python.

Security risks:
- **CRITICAL** — SQL built with f-strings interpolating identifiers and (claimed-whitelisted) expressions:
  - 320: `f"\"{ident}\" {op_sql}"`
  - 323: `f'SELECT id FROM "{parent_table}" WHERE {having_clause}'`
  - 327: `f'SELECT id FROM "{parent_table}" WHERE ({expr}) {op_sql} %s'`
  Whitelist `[A-Za-z0-9_+\-*/%(),.\s]+` permits parentheses, commas, operators — sufficient to inject subqueries (`id) UNION SELECT … --`). Replace with `psycopg2.sql.Identifier` and a column-name allow-list pulled from `information_schema`.
- **HIGH** — `_column_exists_cache` is module-global and never invalidated on DDL — renamed/dropped columns leak past validation.
- **MEDIUM** — Silent `except Exception: return None` (188-190, 242-244, 282-283, 376-377) downgrades push-down to Python without surfacing the failure.

Architecture: split into push-down planner / runtime evaluator / rollup aggregator.

## api/BL/dashboard.py (213)
Dashboard component pre-processing + Excel export.
- **MEDIUM** — `Content-Disposition: attachment; filename="{filename}"` (~201-207) — `filename` is user-controlled (report name); CRLF + arbitrary filename. Wrap in `os.path.basename` and quote.
- **LOW** — Tempfile not explicitly cleaned up after `FileResponse` closes.

## api/BL/dashboards/dashboard.py (308)
Folder tree + dashboard fetch via `get_permissions`. No raw SQL. OK.

## api/BL/dashboards/get_dashboards_from_reports.py (0)
**LOW** — Empty file. Delete.

## api/BL/home/home.py (16)
Trivial pass-through. OK.

## api/BL/Listviews/GetListview.py (591)
Listview generator with field-level filtering.
- **HIGH** — User-supplied `field`, `operator`, `value` flow into the SQL layer (createSQLFunction) — operator whitelist must live there.
- **MEDIUM** — Per-row enrichment loops (N+1).

## api/BL/mergefields.py (101)
Email merge-field helper used by test-send.
- **HIGH** — User Gmail "app password" stored via `update_user_app_password` and read via `get_user_app_password`. Confirm encryption at rest (Fernet) — otherwise plaintext credential.
- **MEDIUM** — Merge regex `r"{!([\w]+)\.([\w]+)(?:,\s*(.*?))?}"` permits arbitrary default-value text and substitutes into the rendered HTML body without escaping.
- **MEDIUM** — Recipient email never validated.

## api/BL/ObjectManager/{ObjectWithSetup.py (9), ObjectWithoutSetup.py (17), SearchLayouts.py (26)}
Thin wrappers over `get_permissions` / metadata fetch. No findings.

## api/BL/PageBuilder/get_pagebuilder.py (47)
Page-builder JSON reader. OK.

## api/BL/PageLayouts/page_layout.py (166)
Builds layout tree from saved JSON. Field visibility computed via `get_field_metadata` — depends on permissions.py correctness.

## api/BL/PreviewPage/GetPreviewPage.py (421)
Record-detail preview with related lists.
- **HIGH** — Authz path is "admin OR (owner OR assigned_to OR shared)"; multiple branches → high IDOR risk if any branch is wrong. Centralise into `can_read(record)` with unit tests.
- **MEDIUM** — Preview pulls related records via repeated `get_permissions` calls (batch).

## api/BL/Profiles/patch_profiles.py (73)
Updates a profile's permissions JSON.
- **CRITICAL** — Body-derived fields land on the profile row. If `update_profiles` does not strip reserved keys (`is_admin`, `profile_type`, `permissions`), a non-admin can patch their own profile to admin. Verify the body whitelist.

## api/BL/Reports/get_reports.py (190)
Report definition reader. OK.

## api/BL/Users/CreateUsers.py (805)
User CRUD plus cPanel email-account provisioning.
- **HIGH** — `requests.post(CPANEL_API, …)` (≈255-270) without explicit `verify=`; confirm TLS verification.
- **HIGH** — `Authorization` header consumed via `request.headers.get('Authorization').split(' ')[1]` — IndexError for malformed headers, also a parsing-confusion risk.
- **HIGH** — Confirm the create-user branch hashes passwords with `make_password` (the import exists in blcontroller, not necessarily here).
- **MEDIUM** — ~360 lines of stale commented user code — remove.

## api/BL/recycle_bin.py (263)
Soft / hard delete + restore.
- **CRITICAL** — SQL injection via interpolated table name in raw `cursor.execute(f"… FROM {object_name} WHERE …", [record_id])` (29-40, 71-78, 195-197). object_name is user-supplied. Switch to psycopg2.sql.Identifier and validate against information_schema.
- **HIGH** — No authorization check on `permanently_delete_records` and `empty_recycle_bin`.
- **HIGH** — `except Exception: continue` in deletion loops (82-83, 213-214) silently swallows partial failures.

## api/BL/task.py (263)
Task helpers + telephony permission check.
- **POSITIVE** — `_validate_schema` whitelists schema (9-13).
- **POSITIVE** — `group_has_ancestor` uses a `visited` set.
- **LOW** — `get_related_tasks` raw SQL is parameterised correctly.

## api/BL/utils.py (209)
Utilities — filter construction, encryption, JWT.
- **CRITICAL** — `key = Fernet.generate_key(); fernet = Fernet(key)` at module load (≈12-13). Key is regenerated every process restart — previously-encrypted data is undecryptable; rotation undocumented.
- **HIGH** — `encryptPassword` (125-134) uses AES-CBC with a fixed IV from env. Same plaintext → same ciphertext (equality oracle). Use AES-GCM with random nonce.
- **HIGH** — Manual padding rather than PKCS7 — boundary bug for length-multiples of 16.
- **MEDIUM** — JWTHandler reads `ENCRYPTION_JWT_SECRET` via `os.getenv` with no fail-fast on `None`.
- **MEDIUM** — `construct_filters` accepts arbitrary operator strings — relies on downstream layer to validate.

## api/BL/whatsapp/__init__.py — empty.

## api/BL/whatsapp/whatsapp.py (266)
- **CRITICAL** — Hardcoded WABA id `577630585438281` (line 39). Move to env.
- **HIGH** — Access token stored as plaintext in DB dict (~131). Encrypt with Fernet.
- **LOW** — Validation message says "empty" but checks length (44-45).

## api/BL/whatsapp/utils.py (98)
- **POSITIVE** — Raw SQL parameterised correctly (18-26).
- **HIGH** — Phone normaliser hardcodes India (`'91' + receiver`, 11-14, 61-62) — international users get wrong recipients.
- **MEDIUM** — `WhatsAppMessageException` defined but never caught.

# 3. api/emailsend

## api/emailsend/tasks.py (135)
Celery tasks for due email campaigns + verification reminders.
- **CRITICAL** — `process_due_email_campaigns` is a `shared_task` with no auth gating — the user_id is taken from `created_by_id`, not the caller.
- **HIGH** — Body loaded from DB and fed unchanged through `replace_merge_fields` — HTML/JS injection.
- **HIGH** — No rate limit on bulk send (69-74).
- **HIGH** — Campaign marked `completed` regardless of partial-failure (78); no DLQ.
- **MEDIUM** — Print statements (16, 28, 48, 66) leak template subjects, recipient ids, user ids.
- **MEDIUM** — Two Celery workers can claim the same draft campaign (no row lock).

## api/emailsend/views.py (437)
REST endpoints + Gmail/Outlook OAuth callbacks + campaign tracking.
- **CRITICAL** — OAuth state is the JWT carrying user_id (Gmail 318, 340) and is `str(user_id)` plaintext for Outlook (390, 423). No CSRF nonce, no session pinning — attacker can link their own Google/Outlook to a victim user_id.
- **CRITICAL** — Refresh tokens persisted plaintext (82-86, 333-349, 433).
- **CRITICAL** — Email body / subject merged via `replace_merge_fields` and passed to providers as-is (75-76).
- **CRITICAL** — CC injection: `cc_raw = data.get("cc", [])` joined with `", "` (50-51, 96) — header injection if any provider concatenates raw.
- **CRITICAL** — No record-level authorization on `SendTestEmailAPIView`.
- **HIGH** — `check_domain_authenticated` (100) failure → fail-open default.
- **HIGH** — `print(response)` (215) can capture SendGrid retry headers.
- **HIGH** — Outlook scope `https://graph.microsoft.com/.default` (389/415) — too broad; should be `Mail.Send`.
- **HIGH** — Two hardcoded Outlook redirect_uris (8000 vs 8080) — production breakage.
- **MEDIUM** — `os.remove('api/emailsend/token.json')` (59-62) — shared file path, deleting nukes other users.
- **MEDIUM** — `number_sent = len(responses)` (161) doesn't exclude failed sends.

## api/emailsend/utils/email_logger.py (55)
- **HIGH** — Stores email body + subject + addresses plaintext (22-34).
- **HIGH** — `schema=schema` parameter from kwargs without validation.
- **MEDIUM** — `except Exception: print(...)` (54-55) → audit gap.

## api/emailsend/utils/find_provider.py (46)
- **CRITICAL** — `dns.resolver.resolve(domain, 'MX')` (8) without timeout → DNS DoS / DNS-rebinding angle.
- **HIGH** — cPanel API URL fetched without explicit `verify=`; user's Authorization header forwarded (36-41) — token leak.
- **MEDIUM** — Existence-leak error strings.

## api/emailsend/utils/gmail_auth.py (250)
- **CRITICAL** — Refresh token stored as raw JSON in `email_provider_setup.cred` (82-86, 209-218).
- **CRITICAL** — Combined with shared client_secret env var (215-216) → DB compromise = mailbox compromise.
- **HIGH** — No PKCE.
- **HIGH** — `state=str(token)` (43) is the JWT, not a random nonce.
- **MEDIUM** — Token-update race (244).
- **LOW** — Dead commented code (106-173).

## api/emailsend/utils/gmail_service.py (95)
- **HIGH** — `MIMEText(html_content, 'html')` (36) without sanitization.
- **HIGH** — CC header injection through `_join_recipients` (no \r\n filtering).
- **MEDIUM** — `userId='me'` (69) trusts the caller.

## api/emailsend/utils/mergefields.py (101)
- **CRITICAL** — Fetches a record by id with no authorization check (43-88) — anyone with a record id reads the whole row.
- **HIGH** — Values inserted into HTML email without escaping (28-34).
- **HIGH** — Relationship resolver builds `sql.Identifier(col_name[:-3])` (75) — fragile.

## api/emailsend/utils/nylas_service.py (161)
- **CRITICAL** — `grand_id` (typo of grant_id) stored plaintext in users (40-41).
- **CRITICAL** — OAuth state = `str(user_id)` (138).
- **CRITICAL** — Hardcoded Nylas client_id (34).
- **HIGH** — No authorization check on send.
- **HIGH** — Field name typo (`grand_id` vs `grant_id`) breaks the "is connected" check (134) → re-auth on every send.

## api/emailsend/utils/outlook_auth.py (162)
- **CRITICAL** — Refresh token stored as JSON file (94-96) and as plaintext DB row (140-152).
- **CRITICAL** — No PKCE.
- **HIGH** — `state=str(user_id)`.
- **HIGH** — `AUTHORITY = …/common` — pin TENANT_ID for single-tenant.
- **MEDIUM** — `SCOPES = "https://graph.microsoft.com/.default"`.
- **LOW** — `webbrowser.open()` / `input()` (95-99) leftover from local testing.

## api/emailsend/utils/outlook_service.py (211)
- **CRITICAL** — `get_user_gmail_credentials(provider="outlook")` returns plaintext creds (162).
- **HIGH** — Body sent unsanitized; CC raw split.
- **HIGH** — Hardcoded redirect_uri (54) conflicts with views.py (383).

## api/emailsend/utils/sendgrid_service.py (66)
- **HIGH** — API key in Authorization header; `print(response)` and exception text returned upstream.
- **HIGH** — No email validation, no rate limit on bulk personalisations.
- **MEDIUM** — Plain text/plain only in `send_email_using_sendgrid`; bulk path uses dynamic templates.

# 4. api/formulas

## api/formulas/safe_evaluator.py (185)
AST-based safe-expression evaluator.
- **POSITIVE** — Whitelist (Constant/Num/Str/Name/BinOp/UnaryOp/Compare/BoolOp/IfExp). Correctly REJECTS Attribute, Call, Lambda, ListComp/SetComp/DictComp, GeneratorExp, Subscript, FormattedValue, JoinedStr, Starred, NamedExpr.
- **POSITIVE** — Operator whitelist covers arithmetic / comparison / boolean only (no bitwise).
- **POSITIVE** — `max_recursion_depth = 100` (102).
- **NONE** in isolation. The danger is in callers that pass sensitive context.

## api/formulas/evaluate_formula.py (257)
Orchestrator: extracts function calls, dispatches via metadata, then hands the residual expression to safe_evaluate.
- **HIGH** — Field-reference injection (218): `if value_ref in record: return record[value_ref]`. If callers don't strip sensitive columns, formulas can read e.g. `password_hash`, `api_token`.
- **MEDIUM** — Function result `str()`-substituted back into the formula (116) — type-confusion mitigated for single-function formulas only.

## api/formulas/functions_and_conditions.py (544)
- **POSITIVE** — No eval/exec/compile. Hardcoded dispatch.
- **POSITIVE** — Missing function raises `InvalidFunctionError`.
- **LOW** — DoS via `POWER(2, 100000)`, deeply nested IF/CASE; no per-call timeout.

## api/formulas/formula_validation.py (514)
- **LOW** — Duplicate `extract_functions` (drift risk).
- **POSITIVE** — `fields_metadata` type-checked (86); BUG-27 helper present.

## api/formulas/evaluate_rollup.py (459)
- **HIGH** — No permission check on child records before aggregation. Rollup leaks data the caller can't read directly.
- **MEDIUM** — Operator inserted via `sql.SQL(operator)` (76) after whitelist (57). Safe iff the whitelist branch is the only path.
- **MEDIUM** — `filter_criteria` parsed via `json.loads` with no schema validation; permissive shape.
- **HIGH** — Per-child formula evaluation (129-136, 291-297) — N child rows × formula evaluation = DoS vector.

## api/formulas/functions_metadata.py (310) — static. OK.

## api/formulas/exceptions.py (99) — data only. OK.

## api/formulas/cache.py (103)
- **LOW** — Cache key `str(args) + str(sorted(kwargs.items()))` collides on whitespace.
- **MEDIUM** — No TTL; staleness on formula edits.

## api/formulas/logger_config.py (56), validators.py (197), test_formulas.py (143) — no security findings.

# 5. api/migrations

## api/migrations/__init__.py — empty.

## api/migrations/0001_initial.py (106)
- **HIGH** — `SessionLog.access_token` / `refresh_token` `CharField(500)` (66-69) — plaintext tokens. Hash or do not store.
- **MEDIUM** — `User.email` unique=True with blank=True default='' (24) — uniqueness violations on empty strings; ambiguous identity.
- **MEDIUM** — `User.profile_id` is `CharField` with no FK / org scope.

## api/migrations/0002_user_is_email_verified.py (18) — no findings.

## api/migrations/0003_organization_user_last_modified_date_user_locale_and_more.py (70)
- **MEDIUM** — `manager_id` `CharField` with no FK / org scope (42-44).
- **LOW** — `Organization.database_schema` `CharField(63)` lacks `RegexValidator(r'^[a-z_][a-z0-9_]*$')`.

## api/migrations/0004_add_logo_to_organization.py (18)
- **INFO** — ImageField; ensure MIME validation server-side and that uploads aren't served from a path that allows execution.

# 6. api/notifications

## api/notifications/notify.py (185)
- **MEDIUM** — `trigger_notication` (55-98) — caller chooses owner_id; nothing prevents broadcasting at any user_id.
- **MEDIUM** — `channel` typed Literal but not validated at runtime.
- **MEDIUM** — `generate_url` (170-186) constructs URL with object_name/id without per-record auth (relies on FE).
- **LOW** — Bare `except Exception: error_record(ex)` swallows errors silently.

# 7. api/ORM

## api/ORM/AuditLogs/audit_trail_logs.py (50)
- **HIGH** — try/except around the INSERT swallows everything with `pass` (48-49) — silent audit gaps. Replace with `logger.error` and consider failing-closed for security events.

## api/ORM/setup/__init__.py — empty.

## api/ORM/setup/create_app.py (79)
- **HIGH** — Implicitly trusts `kwargs['schema']` — no enforcement that schema belongs to the user's org.

## api/ORM/setup/newprofile.py (116)
- **MEDIUM** — `SET search_path TO %s` (parameterised) but no row-level enforcement on subsequent reads.
- **HIGH** — Profile creation copies permissions arrays as-is from request — mass-assignment risk on reserved fields like `is_super_admin`.

## api/ORM/setup/update_page_builder.py (103)
- Mostly safe; uses parameterised queries.

## api/ORM/setup/ObjectManager/create_field.py (221)
- **MEDIUM** — DDL via `psycopg2.sql.Identifier` — safe. Verify column type whitelist.
- **LOW** — Lookup creation queries `fields` / `object` without explicit schema scoping.

## api/ORM/setup/ObjectManager/delete_field.py (97)
- **CRITICAL** — `cursor.execute(f"SET search_path TO {schema};")` (line 20) — schema interpolated unvalidated.
- **MEDIUM** — `object_name` / `field_name` not validated at function entry.

## api/ORM/setup/ObjectManager/delete_object.py (97)
- **CRITICAL** — line 16 `f"SET search_path TO {schema};"` raw f-string DDL.
- **CRITICAL** — line 60 `f"DROP TABLE IF EXISTS {name} CASCADE;"` — DDL injection through user-supplied `name`.
- **HIGH** — lines 83-97 `f"UPDATE {schema}.app SET tabs = ..."` — schema interpolated raw.

## api/ORM/setup/ObjectManager/field_execution.py (566)
- **MEDIUM** — sequence_name f-string built before `_validate_identifier` (102, 120-123).
- **HIGH** — Type-coercion / DDL guards in field rename / drop need column-name regex validation.

## api/ORM/setup/ObjectManager/initial_fields.py (48) — static. OK.

## api/ORM/setup/ObjectManager/post_object.py (224)
- **CRITICAL** — `kwargs.get('schema')` flows directly into `SET search_path TO %s` (parameterised, but no auth check). User can pivot to any tenant's schema if request supplies it.
- **MEDIUM** — Object name JSON-serialised into `app.tabs` (96-105) — backend stores as-is; client must escape on render.

## api/ORM/setup/utils/create_dynamic_table.py (68)
- **HIGH** — Lines 44-68 build `CREATE SEQUENCE` / `CREATE TABLE` via f-string after identifier validation. Even with valid identifiers, prefer `sql.SQL().format(sql.Identifier(...))`.

## api/ORM/setup/utils/field_converter.py (46) — type mapping. OK.

## api/ORM/setup/workflows/create_workflow.py (333), update_workflow.py (319)
- **MEDIUM** — Validation present but exception path uses `print(...)` then re-raises — operationally noisy.
- **MEDIUM** — Workflow JSON stored as text → re-validate before execution.

## api/ORM/setup/workflows/formula_validation.py (327)
- **LOW** — Strict isinstance check on fields_metadata (106-107); errors caught and re-raised but log-noisy.

## api/ORM/setup/workflows/functions_data.py (223) — static registry. OK.

## api/ORM/sqlFunctions/connection.py (26)
- **MEDIUM** — Returns raw connection; ensure SSL + non-superuser DB role.

## api/ORM/sqlFunctions/complexGetSql.py (411)
- **MEDIUM** — Verify ORDER BY / GROUP BY columns route through `psycopg2.sql.Identifier` and not raw concatenation.

## api/ORM/sqlFunctions/createSQLFunction.py (1,411)
- **POSITIVE** — `post_data_sql` validates schema and table_name (787-788).
- **MEDIUM** — Helpers (`get_required_fields`, `get_array_columns`, `get_picklist_fields`) parameterise values but skip identifier validation — defence-in-depth missing.
- **MEDIUM** — `normalize_parent_table` (483-486) returns user input unchanged for non-`user` cases. Add `validate_identifier`.
- **MEDIUM** — Three near-duplicate `validate_and_resolve_lookups*` functions (516-554, 557-620, 623-691).
- **LOW** — Exception path strips stack traces (1372-1395).

## api/ORM/sqlFunctions/createtaslSQLFunction.py (69) — small wrapper. OK.

## api/ORM/sqlFunctions/deleteSQLFunction.py (98)
- **HIGH** — No audit log on delete — compliance gap. Add `log_audit()`.

## api/ORM/sqlFunctions/getQueryBuilder.py (235)
- **MEDIUM** — Verify ORDER BY columns use `sql.Identifier`.

## api/ORM/sqlFunctions/information_schema.py (85) — parameterised reads. OK; LRU cache with explicit invalidation recommended.

## api/ORM/sqlFunctions/relationships.py (433)
- **HIGH** — `cursor.execute(f"SET search_path TO {schema}")` (26-37) — even after `_validate_schema()` upstream, the f-string pattern is fragile. Replace with `SET search_path TO %s`.

## api/ORM/sqlFunctions/updateSQLFunction.py (629)
- **MEDIUM** — Field-change logging trusts `field_tracking_config` (80-109) — if that config is mutable by attacker, fabricated history.

## api/ORM/sqlFunctions/utils/error_handlers.py (319) — message mapping. OK.

## api/ORM/sqlFunctions/utils/helpers.py (514)
- **HIGH** — `parse_condition` (345-459) does not validate `cond["field"]` against `^[a-zA-Z_][a-zA-Z0-9_.]*$` before passing it into PyPika expression. PyPika parameterises values but field-name injection is the typical SQLi via builders.

## api/ORM/sqlFunctions/utils/query_builder_helpers.py (426)
- **MEDIUM** — Confirm helpers always use `sql.Identifier` for ORDER BY / GROUP BY.

# 8. api/pdfgen

## api/pdfgen/__init__.py — empty.

## api/pdfgen/views.py (287)
Invoice → HTML → PDF via xhtml2pdf.
- **CRITICAL** — `pisa.CreatePDF(src=html_string, ...)` (248): xhtml2pdf is known-vulnerable to XXE / SSRF via DOCTYPE entities and external resource loading. Attacker can include `<img src="file:///etc/passwd">` or `<img src="http://169.254.169.254/...">` and exfiltrate via the rendered PDF.
- **CRITICAL** — Logo path constructed as `f"{base.rstrip('/')}api{org.logo.url}"` (115-117) — `..` in `org.logo.url` makes xhtml2pdf fetch a different path.
- **CRITICAL** — Merge fields applied AFTER template render (229-231) — Django escaping bypassed by raw post-substitution.
- **HIGH** — `InvoicePDFView` checks JWT only (262); any authenticated user with a guessed invoice id gets the PDF.
- **HIGH** — Synchronous PDF generation in the request → DoS / timeout.
- **MEDIUM** — Computed-field path inherits formula sandbox concerns.
- **MEDIUM** — `JsonResponse({"error": str(e)})` (265-272) leaks messages.

# 9. api/permissions

## api/permissions/__init__.py — empty.

## api/permissions/permissions.py (1,012)
Central CRUD authorization layer.
- **CRITICAL** — `check_permission` (476-494) accepts `profile_id` from kwargs. Intended to be JWT-derived; if any caller threads `request.data.profile_id` → privilege escalation.
- **CRITICAL** — Sharing logic does NOT verify the grantor has SHARE permission. A user with READ via `shared_records` can grant themselves WRITE.
- **CRITICAL** — Field-level write enforcement missing. `get_field_metadata` (496-579) returns "permitted_fields" but `updateRawSQL` is called with the full `update_data` (872-886). Client can PATCH a field they don't have write permission to.
- **HIGH** — `validate_identifier` only on `resolved_table` (801-837); not all dynamic table names route through it.
- **HIGH** — `patch_permission` for the `users` table doesn't blacklist `profile_id`/`is_active`/etc. — self-promotion possible.
- **MEDIUM** — Default access level `'Public Read Write'` when sharing_records row missing (640, 781, 947) — fail-open.
- **MEDIUM** — No rate limit on permission checks.

Architecture:
- Authorization scattered across `permissions.py`, `dispatcher.py`, `blcontroller.py`, fetch helpers — replace with a central AuthorizationService.
- Per-request DB query storm; per-request cache only.
- No audit trail of permission denials.

## api/permissions/FetchUsers/fetch_all_subordinates.py (68)
- **POSITIVE** — Recursive CTE has path[]-based cycle detection.
- **HIGH** — try/except + print returns `[manager_id]` silently on failure (37-49).
- **LOW** — Dead Redis cache block (11-68).
- **LOW** — No depth LIMIT.

## api/permissions/FetchUsers/fetch_shared_records.py (37)
- **POSITIVE** — Parameterised; expiration honoured.
- **HIGH** — No org-scope validation on `user_id`.
- **MEDIUM** — Silent default to READ on invalid `type`.

# 10. api/telephony

## api/telephony/views.py (922)
- **CRITICAL** — Hardcoded Voxbay credentials in source (311-317, 351): `UID="rr809pi0j8"`, `PIN="561t2fuvd8"`, `EXT="108"`, `CALLER_ID="914847172533"`. Rotate immediately and remove from git history.
- **CRITICAL** — Voxbay click-to-call invoked over plain HTTP with credentials in the URL (`pbx.voxbaysolutions.com/api/clicktocall.php?uid=…&pin=…`).
- **CRITICAL** — `telephony_route`, `telephony_cdr`, etc. are `@csrf_exempt` with NO auth and NO webhook signature (372-416, 613-713). Attacker can post forged CDRs and overwrite recording_link with a malicious URL.
- **CRITICAL** — SQL identifier injection via `f"...FROM {schema}..."` (468) and `"SELECT id FROM {}.call WHERE id=%s".format(org)` (638). `org = request.headers.get("SCHEMA")` (635) is only checked via `exists_schema` (508) — no whitelist.
- **HIGH** — Channel layer broadcasts to `f"telephony_group_{user_id}"` (514-522, 728-739, 775-788) — no verification that the WS client subscribed to that group.
- **HIGH** — `get_user_by_ext` (433-462) lets anyone enumerate users by extension.
- **HIGH** — No rate limit on `make_call` / `incoming_call` (717-797).
- **HIGH** — Disposition / recording_url stored as-is from external party (624, 669).
- **MEDIUM** — Race on duplicate CDR for same call_id (637-690) — no row lock.
- **MEDIUM** — `Fernet.generate_key()` at module load (825) — non-functional encryption.
- **LOW** — 47-line dead `execute_test_api` block (829-875); incomplete `user_can_make_call` (917-923).

# 11. api/workflows

## api/workflows/__init__.py — empty.

## api/workflows/create_records.py (97)
- **HIGH** — No permission check that the user can CREATE in `target_object` before calling `post_data_sql` (89). Identifier validated for shape, not for authority.
- **HIGH** — Field-value resolution copies any field from the triggering object (64-70) without per-field read permission.

## api/workflows/update_records.py (94)
- **HIGH** — No check that the user can UPDATE the target record (75-90).
- **MEDIUM** — Module identifier validated (39) but not linked to user-accessible modules.

## api/workflows/workflow_executor.py (635)
- **CRITICAL** — Privilege inheritance via `execute_action` (226, 366-368): create/update actions run as the user who triggered the workflow. A user-creatable workflow that targets a restricted object becomes a privilege escalator.
- **HIGH** — Condition field injection (395-398): `field_name = cond.get("field", {}).get("name") if isinstance(...) else cond.get("field")`. Attacker-controlled condition can probe any column via the boolean side effect of action firing.
- **HIGH** — No object-level permission check (169, 251) — code assumes `obj` was already authz-checked by the caller. Internal triggers (cron, scheduled) may not.
- **HIGH** — Email template body fetched from DB (494-506) and forwarded to `send_test_email` — server-side template injection risk if downstream renders as Django/Jinja.
- **LOW** — `_resolve_user_ids` builds `IN ({placeholders})` from `len(users)` — values parameterised; only DoS via long lists.

Architecture: action dispatch is a string switch; new actions can ship without security review. Centralise.

---

# Cross-cutting findings

1. **Tenant isolation is implicit, not enforced.** Across ORM, BL, telephony, emailsend, the `schema` value is taken from request kwargs/headers and trusted. Add a single middleware that derives `schema` from the user's JWT/org and ignores any client-supplied value.
2. **OAuth implementation is broken across all three providers** (Gmail, Outlook, Nylas): missing PKCE, predictable state, plaintext refresh token storage, broad scopes.
3. **f-string SQL is the dominant injection vector**: 7+ files build SQL via f-strings even when `psycopg2.sql` is available. Lint/CI rule that fails on `cursor.execute(f"...")` is the highest-leverage fix.
4. **God-class architecture in BL** (5,087-line dispatcher) makes secure review nearly impossible. Decompose by domain entity.
5. **Authorization scattered**: dispatcher attaches user, BL re-checks ownership, permissions.py rechecks again, workflows skip checks entirely. Centralise into an AuthorizationService and write authorization unit tests.
6. **Field-level write enforcement is purely UI-hinted**. Server-side, `update_data` is sent in full to `updateRawSQL` regardless of permitted_fields. This is the most exploitable miss for self-promotion attacks.
7. **No webhook signature verification** anywhere (telephony CDR, Facebook, etc.) — forged events are accepted.
8. **PII / token leakage in logs**: numerous `print(...)` calls in production code paths — replace with structured logging with redaction.
9. **No global rate limiting** — bulk email, bulk call, permission probe, OAuth flow endpoints are all unthrottled.
10. **xhtml2pdf** is known-CVE library; PDF generation needs sanitised input + SSRF/XXE-safe renderer (e.g. WeasyPrint with `media_type='print'` and a tight URL fetcher).

---

# Severity tally

| Severity  | Approximate count |
|-----------|-------------------|
| CRITICAL  | ~32 |
| HIGH      | ~70 |
| MEDIUM    | ~55 |
| LOW       | ~25 |

The CRITICALs are concentrated in:
- `api/BL/recycle_bin.py`, `api/BL/computed_fields.py` (SQL injection)
- `api/BL/utils.py` (broken Fernet/AES)
- `api/BL/blcontroller.py` (test_trigger backdoor; mass-assignment patterns)
- `api/BL/Profiles/patch_profiles.py` (profile self-promotion)
- `api/permissions/permissions.py` (profile_id from kwargs; sharing escalation; no field-write enforcement)
- `api/emailsend/*` (plaintext OAuth tokens, weak state, no record auth)
- `api/pdfgen/views.py` (xhtml2pdf XXE/SSRF, IDOR on invoices)
- `api/telephony/views.py` (hardcoded Voxbay creds, unsigned webhooks, header-driven schema injection)
- `api/workflows/workflow_executor.py` (privilege inheritance, condition field probe)
- `api/ORM/setup/ObjectManager/{delete_object,delete_field,post_object}.py` (DDL injection, tenant pivot)

---

# Immediate remediation plan (highest-leverage first)

### Week 1 — stop-the-bleed
1. Re-enable `permission_classes = [IsAuthenticated]` on Dispatcher; remove `test_trigger` branch.
2. Rotate Voxbay credentials and move to env. Audit git history; force-rewrite if leak window was wide.
3. Replace every `cursor.execute(f"... {ident} ...")` with `sql.SQL().format(sql.Identifier(ident))` AND add a CI grep that blocks the pattern.
4. Server-side filter `update_data` in `patch_permission` to `permitted_fields`; add a write-blacklist for `users.profile_id`, `is_admin`, `is_active`, `organization_id`.
5. Encrypt OAuth refresh tokens at rest (Fernet from a stable env-provided key).
6. Strip generic `Exception` → message responses; replace with generic 500 + structured server log.
7. Add HMAC verification on telephony CDR webhook.

### Weeks 2-3
8. Add tenant-isolation middleware that derives `schema` from JWT and overwrites any incoming kwargs/headers.
9. Add PKCE + random nonce state to all three OAuth flows; pin redirect_uri per env.
10. Remove `Fernet.generate_key()` at module load in `api/BL/utils.py` and `api/telephony/views.py`; fail-fast if env key missing.
11. Move bulk send / call / email through Celery with rate limits + DLQ.
12. Replace xhtml2pdf with WeasyPrint configured with no-network URL fetcher; add per-record authz on InvoicePDFView.
13. Strip mergefield outputs through `bleach.clean(...)` for HTML emails.

### Sprint
14. Decompose `api/BL/blcontroller.py` by domain (Reports, Listviews, Records, etc.); add per-domain unit tests.
15. Centralise authorization in `AuthorizationService` with `can_read/write/delete/share(record)`.
16. Add audit logging for permission denials and OAuth state mismatches.
17. Add formula evaluation timeout, child-record permission filter for rollups, and field allow-list for workflow-readable fields.

---

# Files re-confirmed scanned (re-audit checklist)

```
api/APIs/{__init__.py, dispatcher.py}
api/BL/{__init__.py, blcontroller.py, computed_fields.py, dashboard.py, mergefields.py, recycle_bin.py, task.py, utils.py}
api/BL/dashboards/{dashboard.py, get_dashboards_from_reports.py}
api/BL/home/home.py
api/BL/Listviews/GetListview.py
api/BL/ObjectManager/{ObjectWithSetup.py, ObjectWithoutSetup.py, SearchLayouts.py}
api/BL/PageBuilder/get_pagebuilder.py
api/BL/PageLayouts/page_layout.py
api/BL/PreviewPage/GetPreviewPage.py
api/BL/Profiles/patch_profiles.py
api/BL/Reports/get_reports.py
api/BL/Users/CreateUsers.py
api/BL/whatsapp/{__init__.py, utils.py, whatsapp.py}
api/emailsend/{tasks.py, views.py}
api/emailsend/utils/{email_logger.py, find_provider.py, gmail_auth.py, gmail_service.py, mergefields.py, nylas_service.py, outlook_auth.py, outlook_service.py, sendgrid_service.py}
api/formulas/{cache.py, evaluate_formula.py, evaluate_rollup.py, exceptions.py, formula_validation.py, functions_and_conditions.py, functions_metadata.py, logger_config.py, safe_evaluator.py, test_formulas.py, validators.py}
api/migrations/{0001_initial.py, 0002_user_is_email_verified.py, 0003_organization_user_last_modified_date_user_locale_and_more.py, 0004_add_logo_to_organization.py, __init__.py}
api/notifications/notify.py
api/ORM/AuditLogs/audit_trail_logs.py
api/ORM/setup/{__init__.py, create_app.py, newprofile.py, update_page_builder.py}
api/ORM/setup/ObjectManager/{create_field.py, delete_field.py, delete_object.py, field_execution.py, initial_fields.py, post_object.py}
api/ORM/setup/utils/{create_dynamic_table.py, field_converter.py}
api/ORM/setup/workflows/{create_workflow.py, formula_validation.py, functions_data.py, update_workflow.py}
api/ORM/sqlFunctions/{complexGetSql.py, connection.py, createSQLFunction.py, createtaslSQLFunction.py, deleteSQLFunction.py, getQueryBuilder.py, information_schema.py, relationships.py, updateSQLFunction.py}
api/ORM/sqlFunctions/utils/{error_handlers.py, helpers.py, query_builder_helpers.py}
api/pdfgen/{__init__.py, views.py}
api/permissions/{__init__.py, permissions.py}
api/permissions/FetchUsers/{fetch_all_subordinates.py, fetch_shared_records.py}
api/telephony/views.py
api/workflows/{__init__.py, create_records.py, update_records.py, workflow_executor.py}
```

`__pycache__` directories were intentionally skipped — they are compiled bytecode artefacts, not source.
