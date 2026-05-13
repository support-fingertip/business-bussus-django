# Runbook — Suspected cross-tenant data leak

**Severity:** P1 (always)
**Audience:** On-call + security lead + engineering management

A cross-tenant leak is the worst-case failure mode for this platform.
The goal of this runbook is **contain in minutes, communicate within
hours, remediate within days**.

## 0. Triggers — any of these is in scope

- `TenantViolation` alert fires.
- Hourly cross-tenant heartbeat fails.
- RLS heartbeat returns non-zero count.
- A customer reports seeing another customer's data.
- A bug bounty / pen test finding.
- A backup-restore mix-up confirmed in ops.

## 1. Contain (within 15 minutes)

1. **Page security lead + engineering on-call.** Open the incident channel (template: `#sec-incident-<date>`).
2. **Stop the bleeding** depending on suspected vector:
   - JWT/auth-layer leak: **rotate `JWT_SECRET_KEY`** → all tokens invalidated globally → force re-login.
   - Specific endpoint: deploy a feature flag that returns 503 for that endpoint.
   - DB role / RLS issue: revoke the offending role's grants temporarily.
   - Background job: stop the relevant Celery queue.
3. **Snapshot evidence**:
   - Copy relevant log lines and audit entries to the incident channel.
   - Take a DB snapshot if there's risk of state changing during investigation.

## 2. Triage (within 1 hour)

Establish:

- **Scope**: which tenants' data, which records, how many.
- **Root cause hypothesis**: which layer(s) failed.
- **Time window**: when the leak started, when it ended (or whether ongoing).
- **Access vector**: who accessed the data — internal staff, another tenant's user, automated job, external attacker.

Use the audit log (`audit_trail_track`) + application logs + DB logs.
Filter by `tenant_id` mismatches: requests where the requesting user's
`org_id` differs from the accessed record's `organization_id`.

## 3. Notify (within 24-72 hours)

GDPR Article 33 / 34 timeline: notify the supervisory authority within
72 hours of becoming aware. Customer notification timing per contract +
applicable law.

Coordinate with:
- Legal counsel (drafts customer notification)
- Sales/CS (handles customer communication channel)
- Marketing (handles public communication if needed)

Notification must include:
- What happened
- What data was involved
- What we've done to contain it
- What the customer should do
- A point of contact for questions

## 4. Remediate (within 1-5 days)

1. **Fix the root cause** — code change, infra change, process change.
2. **Add a regression test** that would have caught this.
3. **Add a runtime check** that would detect a recurrence.
4. **Update the threat model** if a new attack class was discovered.
5. **Restore service** with the fix verified in staging.

## 5. Post-mortem (within 2 weeks)

- Blameless post-mortem template.
- Timeline of detection / response / resolution.
- 5-whys root cause analysis.
- Action items with owners + due dates.
- Distributed internally; severe incidents get a customer-facing summary.

## 6. Follow-up

- Verify every action item is closed.
- Run the regression test in CI permanently.
- Tabletop the scenario at the next quarterly drill.

## Roles

| Role | Responsibility |
|---|---|
| Incident commander | Coordinates, decides containment, owns customer comms approval |
| Security lead | Owns triage, evidence, remediation plan |
| On-call engineer | Implements containment, runs queries |
| Legal counsel | Owns notification language, regulatory timing |
| CS lead | Owns customer communication channel |

## Templates

- Customer notification draft: `docs/security/templates/customer_notification.md` (TODO Phase 11)
- Authority notification draft: `docs/security/templates/regulator_notification.md` (TODO Phase 11)
- Post-mortem template: `docs/runbooks/postmortem_template.md` (TODO Phase 11)
