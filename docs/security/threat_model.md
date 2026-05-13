# Threat model — multi-tenant launch readiness

**Status:** Draft
**Date:** 2026-05-13
**Owner:** Security working group

This document enumerates the cross-tenant attack surfaces and maps
each one to the layer(s) of `docs/adrs/0004-multi-tenant-zero-leak.md`
that defend against it.

## Trust boundaries

The system has the following trust boundaries; data crossing any of
them must carry tenant authorization:

1. Web request (HTTP/WebSocket)
2. Celery task / scheduled job
3. Management command
4. Direct DB connection (`psql`, ops scripts)
5. Backup / restore
6. Cross-system integrations (Salesforce, Facebook, WhatsApp, email, telephony)
7. File storage (object storage, uploaded files)
8. Cache (Redis)
9. Logs and metrics
10. Error reports (Sentry)

## STRIDE — per surface

### 1. Web request

| Threat | Vector | Mitigation layer |
|---|---|---|
| Spoofing | Forged JWT bearing another org's `org_id` | L1 — `resolve_tenant` reconciles against DB |
| Tampering | URL parameter naming another tenant's record id | L3, L4 — manager + RLS reject |
| Repudiation | User claims they didn't perform an action | L5 — `audit_trail_track` append-only |
| Information disclosure | Cross-tenant read via predictable id | L4 — DB role lacks USAGE on other schemas |
| Denial of service | Tenant A floods another tenant's quota | L5 — per-tenant rate limits |
| Elevation of privilege | Profile escalation within an org | L1 — `pin_request_tenant` checks profile-in-schema |

### 2. Celery task

| Threat | Vector | Mitigation layer |
|---|---|---|
| Missing tenant context | Task started without `_tenant_ctx` | L2 — `TenantRequiredTask` base class refuses to run |
| Tenant kwarg trusted from client | Task scheduled with user-supplied schema | L2 — schedulers derive from session, never request body |
| Cross-tenant task (admin) | Nightly billing roll-up | Explicit `AdminTask` base, security-reviewed per PR |

### 3. Management command

| Threat | Vector | Mitigation layer |
|---|---|---|
| Ops operator runs against wrong tenant | Typo in `--tenant` flag | L4 — DB role for the operator + explicit `--confirm-tenant` flag |
| Backfill scripts iterate all orgs | Forgotten tenant scope inside loop | Code-review checklist + L4 (role per tenant) |

### 4. Direct DB connection

| Threat | Vector | Mitigation layer |
|---|---|---|
| DBA reads cross-tenant data | Out-of-band query | L4 — RLS forces even superuser-equivalent role; bastion logs |
| Production DB credentials leaked | Stolen pgpass | L5 — short-lived creds, network ACLs, MFA on bastion |

### 5. Backup / restore

| Threat | Vector | Mitigation layer |
|---|---|---|
| Restore loads tenant A's data into tenant B's schema | Path mix-up | Per-tenant backup + per-tenant restore drill |
| Stolen backup decrypts to plaintext | Compromised backup storage | Backup encrypted with KMS key separate from app role |

### 6. Cross-system integrations

| Threat | Vector | Mitigation layer |
|---|---|---|
| Salesforce webhook lands data in wrong tenant | HMAC verifies; tenant derived from signed callback | `api/security/webhook_verification.py` |
| Facebook lead webhook spoofs page_id | Page id maps to tenant via `lead_capture` | L1 — explicit map; reject unknown page |
| Outgoing email sent under wrong tenant's domain | Template + provider mismatch | Tenant-scoped template + provider lookup at send-time |

### 7. File storage

| Threat | Vector | Mitigation layer |
|---|---|---|
| Path-traversal in uploaded filename | `../../other_org/file.pdf` | `os.path.basename` + UUID-prefixed storage path |
| Object-storage bucket policy too permissive | Cross-tenant signed-URL access | Per-tenant prefix + IAM policy restricted to the tenant role |
| Malware in upload | Trojan PDF | Phase 4.2 ClamAV / cloud malware scanner |

### 8. Cache

| Threat | Vector | Mitigation layer |
|---|---|---|
| Redis key collision | Two tenants share a cache key | L5 — `tenant:<org_id>:` prefix enforced via wrapper |
| Cache poisoning by tenant A bleeds to tenant B | Same root cause | Same |

### 9. Logs and metrics

| Threat | Vector | Mitigation layer |
|---|---|---|
| Tenant A's PII visible to support staff querying logs for tenant B | Logs not tagged | All log lines + metrics carry `tenant_id` tag |
| Sensitive payload (JWT, token, password) logged | Verbose logging in BL | `SafeLogFilter` redacts; Phase 5.2 |

### 10. Sentry

| Threat | Vector | Mitigation layer |
|---|---|---|
| Stack trace contains tenant data in variables | Default Sentry behaviour | `send_default_pii=False`, scrubber rules |

## Residual risks (accept, monitor)

1. **Postgres or Django zero-day** — patch promptly; WAF.
2. **Compromised app server with root** — short-lived creds; ephemeral compute.
3. **Insider DBA** — separation of duties; break-glass + audit.
4. **Side channels** (timing, error-message differences) — uniform 404; constant-time response for sensitive endpoints.
5. **Backup-store compromise** — per-tenant DEK + HSM-backed KEK.

## Review cadence

- Tabletop exercise: quarterly.
- Threat model update: every new external integration or major feature.
- External pen test: pre-launch + annually.
