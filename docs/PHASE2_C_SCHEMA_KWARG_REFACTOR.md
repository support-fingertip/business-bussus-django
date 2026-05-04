# Phase 2.C — `kwargs.get('schema')` → `get_validated_schema(kwargs)`

The audit flagged ~140 sites where Python code reads `schema` from a
`**kwargs` dict and uses it without verifying it matches the
canonical `request.tenant_schema` set by Phase 1's
`schema_authority.pin_request_tenant`. Without verification, a buggy
or malicious downstream caller can mutate the kwarg to inject a
different tenant's schema and read/write the wrong tenant's data.

Phase 2.C migrates those reads to a small helper that performs the
verification. This branch lands the helper + the highest-leverage 35
sites in `api/permissions/permissions.py`. The remaining ~103 sites
across BL/ORM/utils are mechanical follow-ups.

## What changed

### New helper

`api/security/schema_authority.get_validated_schema(kwargs)` —
single-line wrapper over the existing `assert_pinned_schema(request,
schema)`:

```python
def get_validated_schema(kwargs: dict) -> Optional[str]:
    return assert_pinned_schema(
        kwargs.get("request"), kwargs.get("schema")
    )
```

Behaviour:
- **No request in kwargs** (background task, mgmt command) → returns
  the kwarg as-is.
- **Request without `tenant_schema`** (auth bypassed somehow) →
  returns the kwarg as-is.
- **Request pinned + kwarg matches** → returns the pinned value.
- **Request pinned + kwarg mismatches** →
  - `SCHEMA_AUTHORITY_ENFORCE=1` (default): raises `TenantViolation`.
  - `SCHEMA_AUTHORITY_ENFORCE=0` (soak mode): logs WARNING, returns
    pinned.

### Migration pattern

```python
# Before
def some_function(**kwargs):
    schema = kwargs.get('schema')
    # ... use schema ...

# After
from api.security.schema_authority import get_validated_schema

def some_function(**kwargs):
    schema = get_validated_schema(kwargs)
    # ... use schema ...
```

### Sites converted in this branch

`api/permissions/permissions.py` — **35 live sites collapsed to 7
calls** (the helper is invoked once per function and the result is
reused via a local variable):

| Function | Before | After |
|---|---|---|
| `get_object_details` | `schema = kwargs.get('schema')` (1 site) | `schema = get_validated_schema(kwargs)` |
| `get_all_fields_for_table` | inline `kwargs.get('schema')` (1 site) | inline `get_validated_schema(kwargs)` |
| `check_permission` | `schema = kwargs.get('schema')` (1 site) | `schema = get_validated_schema(kwargs)` |
| `get_field_metadata` | `schema = kwargs.get('schema')` (1 site) | `schema = get_validated_schema(kwargs)` |
| `get_permissions` | hoisted `schema` + 3 inline reads | hoisted `get_validated_schema` + locals |
| `post_permission` | 1 inline | hoisted local + reuse |
| `patch_permission` | hoisted `schema` + 5 inline reads | hoisted `get_validated_schema` + locals |
| `delete_permission` | 5 inline reads | hoisted local + reuse |

### Tests added

`tests/security/test_get_validated_schema.py` — covers all four
branches (no request, request without pin, kwarg matches, kwarg
mismatches in enforce + soak modes).

## Remaining sites (Phase 2.C wave 2) — ✅ COMPLETE

Wave 2 landed in commit `ece4ac5`. All 105 remaining sites across 32
files are now migrated. **The repo has zero live
`kwargs.get('schema')` references outside docstrings / comments / the
helper module itself.**

Volume by file:

| File | Sites |
|---|---|
| `api/BL/blcontroller.py` | 28 |
| `api/BL/Profiles/patch_profiles.py` | 13 |
| `api/BL/Listviews/GetListview.py` | 8 |
| `api/BL/recycle_bin.py` | 4 |
| `api/ORM/setup/ObjectManager/post_object.py` | 3 |
| `api/ORM/sqlFunctions/relationships.py` | 3 (default `''`) |
| `api/ORM/sqlFunctions/updateSQLFunction.py` | 3 |
| `api/BL/task.py` | 2 |
| `api/BL/PageBuilder/get_pagebuilder.py` | 2 |
| `api/BL/dashboards/dashboard.py` | 2 |
| `api/BL/home/home.py` | 2 |
| `api/ORM/setup/update_page_builder.py` | 2 |
| `api/ORM/setup/workflows/create_workflow.py` | 2 |
| `api/ORM/sqlFunctions/createSQLFunction.py` | 2 |
| `api/ORM/sqlFunctions/information_schema.py` | 2 |
| `api/emailsend/utils/gmail_auth.py` | 2 |
| `api/emailsend/utils/outlook_service.py` | 2 |
| `utils/field_tracking.py` | 2 |
| `utils/usergroup_utils.py` | 2 |
| 13 more files | 1 each |

Total: 105 live sites converted across 32 files.

The `api/security/schema_authority.py` file itself has self-references
in docstrings (the migration pattern is documented there). Those stay.

## Rollout plan

### Stage 1 — soak in staging (1 week)
Deploy this branch with `SCHEMA_AUTHORITY_ENFORCE=0` (soak mode).
The helper logs a WARNING for every kwarg/pinned mismatch but
doesn't break the request. Monitor production logs for the message:

```
Schema authority violation: caller passed schema='X' but tenant is pinned to 'Y'
(log-only mode; SCHEMA_AUTHORITY_ENFORCE=0)
```

If you see hits, those are real bugs upstream — the caller is
passing the wrong schema. Fix the caller, redeploy, soak again.

### Stage 2 — enforce in staging (1 week)
After 7 days of zero soak warnings, set `SCHEMA_AUTHORITY_ENFORCE=1`.
Mismatches now raise `TenantViolation` (HTTP 403).

### Stage 3 — enforce in production
Same as stage 2, in production, with the 1-week soak preceding.

### Stage 4 — finish the migration (Phase 2.C wave 2)
Convert the remaining ~103 sites in BL/ORM/utils. Each migrated
file gets the same dual treatment.

### Stage 5 — remove `request.schema` legacy attribute
Once all 140 sites read `request.tenant_schema` (via the helper),
the legacy `request.schema` populated by `Dispatcher._init_request_context`
can be deleted. That's a Phase 4 cleanup.

## Risks

- **False positives during soak**: a function legitimately uses a
  different schema (e.g., `public.organizations` lookup from a
  per-tenant request). The kwarg would be `'public'` while the pin
  is the tenant. Watch for this in soak logs and either route those
  calls through a different code path or accept the WARNING noise.
- **Background tasks without pin**: if a Celery task calls a
  permissions function without first opening `with_tenant_schema()`,
  the helper returns the kwarg as-is — no enforcement. Risk #4 from
  the earlier review covered this but the helper doesn't bridge it.
- **Helper invocation cost**: each call validates the kwarg vs.
  pinned. The check is one attribute access + one string compare —
  negligible. The optional log call is the only allocation.

## Rollback

Set `SCHEMA_AUTHORITY_ENFORCE=0` and the helper reverts to log-only
behavior. The kwarg is still respected when the pin isn't set, so
background-task and legacy code paths keep working.
