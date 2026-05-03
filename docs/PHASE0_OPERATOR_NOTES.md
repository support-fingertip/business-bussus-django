# Phase 0 — Operator Notes

These changes harden the security baseline. Some require operator action
**before** deploying this branch, otherwise affected flows will fail fast
(by design — better to fail loudly than serve insecure responses).

## Required environment variables

Copy `.env.example` to `.env` and populate the following **new** keys.

### `OAUTH_TOKEN_ENC_KEY` (REQUIRED)

OAuth refresh tokens stored in `email_provider_setup.cred` are now
encrypted at rest. Without this key, gmail/outlook auth flows will raise.

```bash
# Generate a Fernet key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Store it in your secrets manager (Vault / AWS Secrets Manager / Doppler)
and inject into the runtime. To rotate later, set `OAUTH_TOKEN_ENC_KEYS`
to a comma-separated list (newest first) — decrypt falls back through the
list.

After deploying the code, run the data migration once per environment:

```bash
python manage.py shell -c "exec(open('scripts/migrate_email_provider_setup_encryption.py').read())"
```

The script is idempotent — it skips rows already encrypted.

### `SENTRY_DSN` (recommended, optional)

If unset, Sentry initialization is skipped silently. To enable, register
a project at sentry.io and paste the DSN.

### Voxbay credentials (REQUIRED if telephony is in use)

The following were **hardcoded in `api/telephony/views.py` lines 311–315**
and have been moved to env vars. **Rotate with Voxbay before deploying**
because the previous values were committed to git history.

```
VOXBAY_UID
VOXBAY_PIN
VOXBAY_EXT             (default 108)
VOXBAY_CALLER_ID
VOXBAY_DESTINATION_NUMBER
VOXBAY_AGENT_DIAL_NUMBER
```

### `VOXBAY_WEBHOOK_SECRET` (REQUIRED if telephony is in use)

Voxbay must now sign every webhook body with HMAC-SHA256. Configure on
the Voxbay dashboard to send:

```
X-Voxbay-Signature: sha256=<hex digest>
```

…over the raw POST body, using the secret you provide in the dashboard
**and** in this env var. Endpoints affected:

- `/telephony/route/<id>`
- `/telephony/connecting`
- `/telephony/hangup`
- `/telephony/cdr`
- `/telephony/outgoing`
- `/incoming-call/`

#### Rolling out without breakage

Until Voxbay is configured to send the signature, set
`VOXBAY_WEBHOOK_ENFORCE=0`. The signature is still validated and every
mismatch is logged, but requests are accepted. **Flip to 1 (default)**
once you've confirmed in logs that all live traffic is signed correctly.

## Code changes summary

| Item | Purpose | File(s) |
|---|---|---|
| 0.1 | Restored `IsAuthenticated` (was commented out) | `api/APIs/dispatcher.py` |
| 0.2 | Closed table-name SQL injection in recycle bin; routed through permission gate | `api/BL/recycle_bin.py` |
| 0.3 | Closed `DROP TABLE` SQL injection on custom-object delete | `api/ORM/setup/ObjectManager/delete_object.py` |
| 0.4 | Parameterized `SET search_path` in field delete | `api/ORM/setup/ObjectManager/delete_field.py` |
| 0.5 | Closed dynamic-INSERT SQL injection on app create | `api/ORM/setup/create_app.py` |
| 0.6 | Voxbay creds → env vars | `api/telephony/views.py` |
| 0.7 | `sql.Identifier` for every `{schema}.<table>` site in telephony | `api/telephony/views.py` |
| 0.8 | OAuth refresh tokens encrypted at rest (Fernet) | `api/security/token_encryption.py`, `api/emailsend/utils/gmail_auth.py`, `scripts/migrate_email_provider_setup_encryption.py` |
| 0.9 | HMAC verification on every Voxbay webhook | `api/security/webhook_verification.py`, `api/telephony/views.py` |
| 0.10 | Sanitized 5xx responses (no DB exception text leak) | `api/APIs/dispatcher.py` |
| 0.11 | Sentry SDK integrated (Django + Celery + logging) | `version2/settings.py` |
| 0.12 | Pre-commit hook bans new f-string SQL | `scripts/check_no_fstring_sql.py`, `.pre-commit-config.yaml` |

## Pre-deploy checklist

- [ ] `OAUTH_TOKEN_ENC_KEY` set; data migration executed on staging then prod.
- [ ] Voxbay creds rotated and populated in env.
- [ ] Voxbay configured to sign webhook bodies; `VOXBAY_WEBHOOK_ENFORCE=0` for soak window.
- [ ] `SENTRY_DSN` set (recommended).
- [ ] Sanity test: anonymous request to any `/api/...` returns 401.
- [ ] Sanity test: send a Voxbay test event without signature → confirm rejection (or log entry if soak mode).
- [ ] Sanity test: connect a Gmail account, verify token refreshes after expiry → confirm `cred` row in DB starts with `ENC1:`.
- [ ] Pre-commit hook installed (`pre-commit install`) so future PRs can't add new f-string SQL.

## Known follow-ups (out of Phase 0 scope)

These remain and are tracked in the master plan:

- 9 pre-existing legacy f-string-SQL sites in `BL/Listviews/GetListview.py`,
  `pdfgen/views.py`, `workflows/workflow_executor.py`, `ORM/sqlFunctions/relationships.py`,
  and one residual telephony site. Pre-commit hook only blocks new ones; these
  are scheduled for Phase 2.
- `permissions.py` `IsAuthenticated`-equivalent logic is restored at the
  framework level, but per-record authz fixes (default-deny, TOCTOU) are
  Phase 2.
