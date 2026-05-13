# Runbook — Rotate encryption keys

**Status:** Skeleton (Phase 3 fills in real values)
**Cadence:** Annually OR on suspected compromise
**Audience:** Platform engineering

## Keys in scope

1. **`OAUTH_TOKEN_ROOT_KEK`** — the root key from which per-tenant DEKs are derived.
2. **`OAUTH_TOKEN_ENC_KEYS`** — comma-separated Fernet keys for the encrypted-at-rest token columns.
3. **`SECRET_KEY`** — Django session/CSRF signing key.
4. **`JWT_SECRET_KEY`** — JWT signing key.
5. **Database role passwords** (`bussus_app`, `tenant_<schema>_role` if you give them passwords).
6. **Per-tenant DEKs** — derived from KEK; rotated by regenerating from the KEK via HKDF, possibly with a salt bump.

## Rotation procedure — Fernet token keys (most common)

`MultiFernet` supports multi-key decryption — old keys can decrypt, the
**first** key encrypts new writes. Rotation is therefore non-disruptive.

1. **Generate the new key**
   ```bash
   NEW_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
   ```
2. **Prepend to `OAUTH_TOKEN_ENC_KEYS`** in the secrets manager:
   `OAUTH_TOKEN_ENC_KEYS=$NEW_KEY,<existing keys...>`
3. **Deploy** — restart workers picks up the new key list.
4. **Re-encrypt** existing rows by running:
   ```bash
   python manage.py reencrypt_tokens --table session_log --batch 500
   python manage.py reencrypt_tokens --table email_provider_setup --batch 500
   # … one per table from Phase 3
   ```
5. **Verify** — no rows still encrypted with old key (check by attempting decrypt with new-only key in a dry-run command).
6. **Retire** — after 30 days with no incidents, drop the old key from `OAUTH_TOKEN_ENC_KEYS`. Redeploy.

## Rotation — JWT_SECRET_KEY

Rotating this **invalidates all live tokens** — users will be forced to re-login.

1. Generate: `python -c "import secrets; print(secrets.token_urlsafe(64))"`
2. Replace `JWT_SECRET_KEY` in secrets manager.
3. Deploy.
4. Announce maintenance window OR accept the customer-visible re-login event.

For emergency rotation (suspected token theft), do not announce — rotate immediately.

## Rotation — SECRET_KEY

This invalidates session cookies + password-reset links + CSRF tokens.
Similar to JWT rotation but the blast radius is sessions (less impactful — users mostly use JWT).

Procedure: generate, replace, deploy.

## Rotation — DB role passwords

1. Generate new password via your secrets manager.
2. Apply to Postgres: `ALTER ROLE bussus_app WITH PASSWORD '$new';`
3. Update secrets-manager entry consumed by the app.
4. Trigger a rolling restart.
5. Confirm app reconnects with new password (watch for `FATAL: password authentication failed` in logs).

## Audit

After any rotation:
- Log the rotation event with timestamp + operator id to the central audit store.
- Update the key-rotation calendar (next-due-date).

## Compromise response

If a key is suspected compromised:
- Treat as a P1 incident (`docs/runbooks/incident_response_cross_tenant_leak.md`).
- Rotate immediately; do not delay for customer-friendly timing.
- Identify what the compromised key could have unlocked, contain that data.
