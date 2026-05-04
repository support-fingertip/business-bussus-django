"""Phase 3.B — register Wave 6-8 tenant-scoped models in Django state.

Same pattern as 0005 + 0006: ``managed = False`` +
``SeparateDatabaseAndState`` with empty ``database_operations``.
Tables already exist per-tenant from default_tables.sql; Django
doesn't run DDL.

Adds 13 models:

  Wave 6 — integration / telephony / email (7):
    TelephonyConfig, LandingNumber, TelephonyUser, CallActivity,
    EmailProviderSetup, UserGmailToken, UserOutlookToken

  Wave 7 — audit / history (3):
    AuditTrailTrack, FieldHistoryLog, FieldTrackingConfig

  Wave 8 — misc (3):
    Task, Notification, SharedRecord

(``org_company`` is intentionally NOT modeled — its DDL in
default_tables.sql is fully commented out, the table doesn't exist
in production tenants. See docs/UNSOURCED_DDL.md.)

After this migration the tenant-model coverage is 48/49 = 98%.

See ``docs/PHASE3_B_OPERATOR_NOTES.md`` for the rollout plan.
"""

from __future__ import annotations

from django.contrib.postgres.fields import ArrayField
from django.db import migrations, models


def _id_field():
    return models.CharField(max_length=64, primary_key=True, serialize=False)


def _fk(*, db_column, related_name, to, null=False, blank=False):
    kwargs = {
        "db_column": db_column,
        "db_constraint": False,
        "on_delete": models.deletion.DO_NOTHING,
        "to": to,
    }
    if related_name is not None:
        kwargs["related_name"] = related_name
    if null:
        kwargs["null"] = True
    if blank:
        kwargs["blank"] = True
    return models.ForeignKey(**kwargs)


_STATE_OPERATIONS = [
    # ---------------- Wave 6 — integration ----------------
    migrations.CreateModel(
        name="TelephonyConfig",
        fields=[
            ("id", _id_field()),
            ("provider", models.CharField(blank=True, max_length=50, null=True)),
            ("target_object", models.CharField(blank=True, max_length=100, null=True)),
            ("target_field", models.CharField(blank=True, max_length=100, null=True)),
            ("display_fields", ArrayField(models.TextField(), blank=True, default=list, null=True)),
            ("disposition_values", ArrayField(models.TextField(), blank=True, default=list, null=True)),
            ("status", models.BooleanField(default=True)),
            ("authtoken", models.CharField(blank=True, max_length=512, null=True)),
            ("sid", models.CharField(blank=True, max_length=512, null=True)),
            ("created_by_id", models.CharField(blank=True, max_length=64, null=True)),
            ("last_modified_by_id", models.CharField(blank=True, max_length=64, null=True)),
            ("deleted_by_id", models.CharField(blank=True, max_length=64, null=True)),
            ("is_deleted", models.BooleanField(default=False)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("last_modified_date", models.DateTimeField(blank=True, null=True)),
            ("deleted_date", models.DateTimeField(blank=True, null=True)),
        ],
        options={
            "verbose_name": "Telephony Config",
            "verbose_name_plural": "Telephony Configs",
            "db_table": "telephony_config",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="LandingNumber",
        fields=[
            ("id", _id_field()),
            ("telephony_id", models.CharField(blank=True, max_length=100, null=True)),
            ("landing_number", models.CharField(blank=True, max_length=20, null=True)),
            ("group_name", models.CharField(blank=True, max_length=100, null=True)),
            ("routing_logic", models.CharField(blank=True, max_length=20, null=True)),
            ("status", models.BooleanField(default=True)),
            ("group_id", models.TextField(blank=True, null=True)),
            ("created_by_id", models.CharField(blank=True, max_length=64, null=True)),
            ("last_modified_by_id", models.CharField(blank=True, max_length=64, null=True)),
            ("deleted_by_id", models.CharField(blank=True, max_length=64, null=True)),
            ("is_deleted", models.BooleanField(default=False)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("last_modified_date", models.DateTimeField(blank=True, null=True)),
            ("deleted_date", models.DateTimeField(blank=True, null=True)),
        ],
        options={
            "verbose_name": "Landing Number",
            "verbose_name_plural": "Landing Numbers",
            "db_table": "landing_numbers",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="TelephonyUser",
        fields=[
            ("id", _id_field()),
            ("config_name", models.CharField(blank=True, max_length=50, null=True)),
            ("user_id", models.CharField(max_length=64)),
            ("details", models.JSONField(blank=True, null=True)),
            ("status", models.BooleanField(default=True)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("updated_date", models.DateTimeField(blank=True, null=True)),
        ],
        options={
            "verbose_name": "Telephony User",
            "verbose_name_plural": "Telephony Users",
            "db_table": "telephony_user",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="CallActivity",
        fields=[
            ("id", _id_field()),
            ("data", models.JSONField(blank=True, null=True)),
            ("user_id", models.CharField(blank=True, max_length=64, null=True)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("updated_date", models.DateTimeField(blank=True, null=True)),
        ],
        options={
            "verbose_name": "Call Activity",
            "verbose_name_plural": "Call Activities",
            "db_table": "callactivity",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="EmailProviderSetup",
        fields=[
            ("id", _id_field()),
            ("user_id", models.CharField(max_length=64, unique=True)),
            ("provider", models.CharField(
                choices=[("gmail", "Gmail"), ("outlook", "Outlook"),
                         ("sendgrid", "SendGrid")],
                max_length=50,
            )),
            ("cred", models.JSONField(blank=True, null=True)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("created_at", models.DateTimeField(blank=True, null=True)),
            ("updated_at", models.DateTimeField(blank=True, null=True)),
        ],
        options={
            "verbose_name": "Email Provider Setup",
            "verbose_name_plural": "Email Provider Setups",
            "db_table": "email_provider_setup",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="UserGmailToken",
        fields=[
            ("id", _id_field()),
            ("user_id", models.CharField(max_length=64, unique=True)),
            ("access_token", models.TextField(blank=True, null=True)),
            ("refresh_token", models.TextField(blank=True, null=True)),
            ("token_type", models.TextField(blank=True, null=True)),
            ("expires_in", models.IntegerField(blank=True, null=True)),
            ("expiry_time", models.DateTimeField(blank=True, null=True)),
            ("created_at", models.DateTimeField(blank=True, null=True)),
            ("updated_at", models.DateTimeField(blank=True, null=True)),
        ],
        options={
            "verbose_name": "User Gmail Token",
            "verbose_name_plural": "User Gmail Tokens",
            "db_table": "user_gmail_tokens",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="UserOutlookToken",
        fields=[
            ("id", _id_field()),
            ("user_id", models.CharField(max_length=64, unique=True)),
            ("access_token", models.TextField(blank=True, null=True)),
            ("refresh_token", models.TextField(blank=True, null=True)),
            ("token_type", models.TextField(blank=True, null=True)),
            ("expires_in", models.IntegerField(blank=True, null=True)),
            ("expiry_time", models.DateTimeField(blank=True, null=True)),
            ("created_at", models.DateTimeField(blank=True, null=True)),
            ("updated_at", models.DateTimeField(blank=True, null=True)),
        ],
        options={
            "verbose_name": "User Outlook Token",
            "verbose_name_plural": "User Outlook Tokens",
            "db_table": "user_outlook_tokens",
            "managed": False,
        },
    ),

    # ---------------- Wave 7 — audit ----------------
    migrations.CreateModel(
        name="AuditTrailTrack",
        fields=[
            ("id", _id_field()),
            ("source_namespace_prefix", models.CharField(blank=True, max_length=100, null=True)),
            ("action", models.TextField()),
            ("section", models.CharField(max_length=100)),
            ("is_delegate_user", models.BooleanField()),
            ("changed_at", models.DateTimeField()),
            ("user_id", models.CharField(blank=True, max_length=64, null=True)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
        ],
        options={
            "verbose_name": "Audit Trail Track",
            "verbose_name_plural": "Audit Trail Tracks",
            "db_table": "audit_trail_track",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="FieldHistoryLog",
        fields=[
            ("id", _id_field()),
            ("object_name", models.CharField(max_length=255)),
            ("record_id", models.CharField(max_length=255)),
            ("field_name", models.CharField(max_length=255)),
            ("old_value", models.TextField(blank=True, null=True)),
            ("new_value", models.TextField(blank=True, null=True)),
            ("user_id", models.CharField(blank=True, max_length=64, null=True)),
            ("changed_at", models.DateTimeField()),
            ("created_date", models.DateTimeField(blank=True, null=True)),
        ],
        options={
            "verbose_name": "Field History Log",
            "verbose_name_plural": "Field History Log Entries",
            "db_table": "field_history_log",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="FieldTrackingConfig",
        fields=[
            ("id", _id_field()),
            ("object_name", models.CharField(max_length=255)),
            ("field_name", models.CharField(max_length=255)),
            ("is_tracked", models.BooleanField()),
            ("created_date", models.DateTimeField(blank=True, null=True)),
        ],
        options={
            "verbose_name": "Field Tracking Config",
            "verbose_name_plural": "Field Tracking Configs",
            "db_table": "field_tracking_config",
            "managed": False,
            "unique_together": {("object_name", "field_name")},
        },
    ),

    # ---------------- Wave 8 — misc ----------------
    migrations.CreateModel(
        name="Task",
        fields=[
            ("id", _id_field()),
            ("name", models.CharField(blank=True, max_length=16)),
            ("subject", models.CharField(max_length=512)),
            ("description", models.TextField(blank=True, null=True)),
            ("status", models.CharField(max_length=255)),
            ("due_date", models.DateField()),
            ("related_to_object_id", models.CharField(blank=True, max_length=64, null=True)),
            ("assigned_to_id", models.CharField(blank=True, max_length=64, null=True)),
            ("organisation", models.CharField(blank=True, max_length=64, null=True)),
            ("owner_id", models.CharField(blank=True, max_length=64, null=True)),
            ("created_by_id", models.CharField(blank=True, max_length=64, null=True)),
            ("last_modified_by_id", models.CharField(blank=True, max_length=64, null=True)),
            ("deleted_by_id", models.CharField(blank=True, max_length=255, null=True)),
            ("is_deleted", models.BooleanField(default=False)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("last_modified_date", models.DateTimeField(blank=True, null=True)),
            ("deleted_date", models.DateTimeField(blank=True, null=True)),
            ("object", _fk(db_column="object_id", related_name="tasks",
                           to="api.platformobject", null=True, blank=True)),
        ],
        options={
            "verbose_name": "Task",
            "verbose_name_plural": "Tasks",
            "db_table": "task",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="Notification",
        fields=[
            ("id", _id_field()),
            ("owner_id", models.CharField(max_length=64)),
            ("title", models.CharField(blank=True, max_length=255, null=True)),
            ("message", models.TextField()),
            ("channel", models.CharField(
                choices=[("email", "Email"), ("whatsapp", "WhatsApp"),
                         ("app", "App"), ("sms", "SMS"), ("push", "Push")],
                max_length=20,
            )),
            ("type", models.CharField(
                choices=[("verification", "Verification"), ("reminder", "Reminder"),
                         ("alert", "Alert"), ("system", "System"), ("chat", "Chat")],
                max_length=50,
            )),
            ("status", models.CharField(
                choices=[("pending", "Pending"), ("sent", "Sent"),
                         ("delivered", "Delivered"), ("read", "Read"),
                         ("failed", "Failed")],
                default="pending", max_length=20,
            )),
            ("priority", models.CharField(
                choices=[("low", "Low"), ("normal", "Normal"), ("high", "High")],
                default="normal", max_length=10,
            )),
            ("metadata", models.JSONField(blank=True, null=True)),
            ("url", models.CharField(blank=True, max_length=2048, null=True)),
            ("created_at", models.DateTimeField(blank=True, null=True)),
            ("updated_at", models.DateTimeField(blank=True, null=True)),
            ("read_at", models.DateTimeField(blank=True, null=True)),
            ("sent_at", models.DateTimeField(blank=True, null=True)),
            ("delivered_at", models.DateTimeField(blank=True, null=True)),
        ],
        options={
            "verbose_name": "Notification",
            "verbose_name_plural": "Notifications",
            "db_table": "notifications",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="SharedRecord",
        fields=[
            ("id", _id_field()),
            ("object_name", models.TextField()),
            ("record_id", models.CharField(max_length=64)),
            ("user_id", models.CharField(max_length=64)),
            ("owner_id", models.CharField(max_length=64)),
            ("access_mask", models.IntegerField()),
            ("row_cause", models.CharField(
                choices=[("OWNER", "Owner"), ("OWD", "Org-Wide Default"),
                         ("MANUAL", "Manual"), ("HIERARCHY", "Role Hierarchy"),
                         ("RULE", "Sharing Rule"), ("PARENT", "Parent Implicit")],
                max_length=32,
            )),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("expires_at", models.DateTimeField(blank=True, null=True)),
        ],
        options={
            "verbose_name": "Shared Record (per-record grant)",
            "verbose_name_plural": "Shared Records (per-record grants)",
            "db_table": "shared_records",
            "managed": False,
        },
    ),
]


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0006_phase3_tenant_models"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=_STATE_OPERATIONS,
        ),
    ]
