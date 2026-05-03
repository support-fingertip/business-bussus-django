"""Phase 2 ORM Wave 2 — register tenant-scoped models in Django state.

These tables already exist per-tenant schema, created by the legacy
hand-rolled DDL. Django doesn't own them: every model in this migration
has ``managed = False`` and we use ``state_operations`` only —
``database_operations`` is empty so ``manage.py migrate`` runs as a
no-op against the actual DB.

When deploying:
  1. Apply this migration on production: ``python manage.py migrate api``
     (it's effectively a fake/state-only registration; no SQL runs).
  2. The TenantSchemaMiddleware sets ``search_path`` per request, so
     ORM queries against these models scope to the right tenant.

If a future migration needs to add columns to one of these tables, do
it in tenant-aware DDL (or via the legacy ``api/ORM/setup/`` flow);
don't flip ``managed=True``.
"""

from __future__ import annotations

from django.db import migrations, models


# All operations are wrapped in SeparateDatabaseAndState so Django's
# state graph knows about the models but no DDL ever runs. The
# ``state_operations`` list mirrors what `makemigrations` would
# generate; ``database_operations`` is empty.

_STATE_OPERATIONS = [
    # -------------------- Object metadata --------------------
    migrations.CreateModel(
        name="PlatformObject",
        fields=[
            ("id", models.CharField(max_length=64, primary_key=True, serialize=False)),
            ("name", models.CharField(max_length=63, unique=True)),
            ("label", models.CharField(blank=True, max_length=255, null=True)),
            ("plural_label", models.CharField(blank=True, max_length=255, null=True)),
            ("record_name", models.CharField(blank=True, max_length=255, null=True)),
            ("description", models.TextField(blank=True, null=True)),
            ("allow_activities", models.BooleanField(null=True)),
            ("allow_bulk_api_access", models.BooleanField(null=True)),
            ("allow_in_chatter_groups", models.BooleanField(null=True)),
            ("allow_reports", models.BooleanField(null=True)),
            ("allow_sharing", models.BooleanField(null=True)),
            ("allow_streaming_api_access", models.BooleanField(null=True)),
            ("enable_licensing", models.BooleanField(null=True)),
            ("show_tab", models.BooleanField(null=True)),
            ("starts_with_vowel_sound", models.BooleanField(null=True)),
            ("track_field_history", models.BooleanField(null=True)),
            ("datatype", models.CharField(blank=True, max_length=64, null=True)),
            ("icon", models.CharField(blank=True, max_length=255, null=True)),
            ("icon_color", models.CharField(blank=True, max_length=32, null=True)),
            ("deployment_status", models.CharField(blank=True, max_length=32, null=True)),
            ("search_status", models.CharField(blank=True, max_length=32, null=True)),
            ("prefix", models.CharField(blank=True, max_length=8, null=True)),
            ("default_access_level", models.CharField(blank=True, max_length=32, null=True)),
            ("type", models.CharField(blank=True, max_length=32, null=True)),
            ("setup", models.BooleanField()),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("last_modified_date", models.DateTimeField(blank=True, null=True)),
        ],
        options={
            "verbose_name": "Object (Platform Metadata)",
            "verbose_name_plural": "Objects (Platform Metadata)",
            "db_table": "object",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="Field",
        fields=[
            ("id", models.CharField(max_length=64, primary_key=True, serialize=False)),
            ("name", models.CharField(max_length=63)),
            ("label", models.CharField(blank=True, max_length=255, null=True)),
            ("datatype", models.CharField(max_length=64)),
            ("required", models.BooleanField(default=False, null=True)),
            ("is_modifiable", models.BooleanField(default=True, null=True)),
            ("parent_object", models.CharField(blank=True, max_length=63, null=True)),
            ("relationship_name", models.CharField(blank=True, max_length=63, null=True)),
            ("pickup_values", models.JSONField(blank=True, null=True)),
            ("sort_alpha", models.BooleanField(null=True)),
            ("first_as_default", models.BooleanField(null=True)),
            ("limit_predefined_values", models.BooleanField(null=True)),
            ("no_skip", models.BooleanField(null=True)),
            ("no_rollback", models.BooleanField(null=True)),
            ("default_value", models.CharField(blank=True, max_length=255, null=True)),
            ("default_value_in_checkbox", models.CharField(blank=True, max_length=32, null=True)),
            ("number_length", models.IntegerField(blank=True, null=True)),
            ("send_mail", models.BooleanField(null=True)),
            ("formula_expression", models.TextField(blank=True, null=True)),
            ("formula_return_type", models.CharField(blank=True, max_length=32, null=True)),
            ("summarized_object", models.CharField(blank=True, max_length=63, null=True)),
            ("rollup_type", models.CharField(blank=True, max_length=32, null=True)),
            ("field_to_aggregate", models.CharField(blank=True, max_length=63, null=True)),
            ("filter_criteria", models.JSONField(blank=True, null=True)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("last_modified_date", models.DateTimeField(blank=True, null=True)),
            (
                "object",
                models.ForeignKey(
                    db_column="object_id",
                    db_constraint=False,
                    on_delete=models.deletion.DO_NOTHING,
                    related_name="fields",
                    to="api.platformobject",
                ),
            ),
        ],
        options={
            "verbose_name": "Field",
            "verbose_name_plural": "Fields",
            "db_table": "fields",
            "managed": False,
            "unique_together": {("object", "name")},
        },
    ),

    # -------------------- Authorization core --------------------
    migrations.CreateModel(
        name="Profile",
        fields=[
            ("id", models.CharField(max_length=64, primary_key=True, serialize=False)),
            ("name", models.CharField(max_length=255)),
            ("profile_type", models.CharField(max_length=64)),
            ("description", models.TextField(blank=True, null=True)),
            ("created_by_id", models.CharField(blank=True, max_length=64, null=True)),
            ("last_modified_by_id", models.CharField(blank=True, max_length=64, null=True)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("last_modified_date", models.DateTimeField(blank=True, null=True)),
        ],
        options={
            "verbose_name": "Profile",
            "verbose_name_plural": "Profiles",
            "db_table": "profile",
            "managed": False,
        },
    ),
    # Role model removed — registry row 'roles' is vestigial (no DDL,
    # no runtime queries). Re-add this CreateModel alongside the DDL
    # if/when the role-hierarchy feature ships.
    migrations.CreateModel(
        name="UserGroup",
        fields=[
            ("id", models.CharField(max_length=64, primary_key=True, serialize=False)),
            ("name", models.CharField(max_length=255)),
            ("description", models.TextField(blank=True, null=True)),
            ("created_by_id", models.CharField(blank=True, max_length=64, null=True)),
            ("last_modified_by_id", models.CharField(blank=True, max_length=64, null=True)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("last_modified_date", models.DateTimeField(blank=True, null=True)),
        ],
        options={
            "verbose_name": "User Group",
            "verbose_name_plural": "User Groups",
            "db_table": "user_group",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="UserGroupUser",
        fields=[
            ("id", models.CharField(max_length=64, primary_key=True, serialize=False)),
            ("user_id", models.CharField(max_length=64)),
            (
                "user_group",
                models.ForeignKey(
                    db_column="user_group_id",
                    db_constraint=False,
                    on_delete=models.deletion.DO_NOTHING,
                    related_name="memberships",
                    to="api.usergroup",
                ),
            ),
        ],
        options={
            "verbose_name": "User Group Membership",
            "verbose_name_plural": "User Group Memberships",
            "db_table": "user_group_users",
            "managed": False,
            "unique_together": {("user_group", "user_id")},
        },
    ),

    # -------------------- Permissions --------------------
    migrations.CreateModel(
        name="ObjectPermission",
        fields=[
            ("id", models.CharField(max_length=64, primary_key=True, serialize=False)),
            ("read", models.BooleanField(default=False)),
            ("write", models.BooleanField(default=False)),
            ("edit", models.BooleanField(default=False)),
            ("delete", models.BooleanField(default=False)),
            ("view_all", models.BooleanField(default=False)),
            ("modify_all", models.BooleanField(default=False)),
            (
                "profile",
                models.ForeignKey(
                    db_column="profile_id",
                    db_constraint=False,
                    on_delete=models.deletion.DO_NOTHING,
                    to="api.profile",
                ),
            ),
            (
                "object",
                models.ForeignKey(
                    db_column="object_id",
                    db_constraint=False,
                    on_delete=models.deletion.DO_NOTHING,
                    related_name="object_permissions",
                    to="api.platformobject",
                ),
            ),
        ],
        options={
            "verbose_name": "Object Permission",
            "verbose_name_plural": "Object Permissions",
            "db_table": "object_permissions",
            "managed": False,
            "unique_together": {("object", "profile")},
        },
    ),
    migrations.CreateModel(
        name="FieldPermission",
        fields=[
            ("id", models.CharField(max_length=64, primary_key=True, serialize=False)),
            ("read_access", models.BooleanField(default=False)),
            ("edit_access", models.BooleanField(default=False)),
            ("write_access", models.BooleanField(default=False, null=True)),
            ("delete_access", models.BooleanField(default=False, null=True)),
            ("read_only", models.BooleanField(null=True)),
            ("visible", models.BooleanField(null=True)),
            (
                "profile",
                models.ForeignKey(
                    db_column="profile_id",
                    db_constraint=False,
                    on_delete=models.deletion.DO_NOTHING,
                    to="api.profile",
                ),
            ),
            (
                "object",
                models.ForeignKey(
                    db_column="object_id",
                    db_constraint=False,
                    on_delete=models.deletion.DO_NOTHING,
                    related_name="field_permissions",
                    to="api.platformobject",
                ),
            ),
            (
                "field",
                models.ForeignKey(
                    db_column="fields_id",
                    db_constraint=False,
                    on_delete=models.deletion.DO_NOTHING,
                    related_name="permissions",
                    to="api.field",
                ),
            ),
        ],
        options={
            "verbose_name": "Field Permission",
            "verbose_name_plural": "Field Permissions",
            "db_table": "field_permissions",
            "managed": False,
            "unique_together": {("field", "profile")},
        },
    ),
    migrations.CreateModel(
        name="TabPermission",
        fields=[
            ("id", models.CharField(max_length=64, primary_key=True, serialize=False)),
            ("type", models.CharField(max_length=32)),
            (
                "profile",
                models.ForeignKey(
                    db_column="profile_id",
                    db_constraint=False,
                    on_delete=models.deletion.DO_NOTHING,
                    to="api.profile",
                ),
            ),
            (
                "object",
                models.ForeignKey(
                    db_column="object_id",
                    db_constraint=False,
                    on_delete=models.deletion.DO_NOTHING,
                    related_name="tab_permissions",
                    to="api.platformobject",
                ),
            ),
        ],
        options={
            "verbose_name": "Tab Permission",
            "verbose_name_plural": "Tab Permissions",
            "db_table": "tab_permissions",
            "managed": False,
            "unique_together": {("object", "profile")},
        },
    ),
    migrations.CreateModel(
        name="AppPermission",
        fields=[
            ("id", models.CharField(max_length=64, primary_key=True, serialize=False)),
            ("app_id", models.CharField(max_length=64)),
            ("access", models.BooleanField(default=False)),
            (
                "profile",
                models.ForeignKey(
                    db_column="profile_id",
                    db_constraint=False,
                    on_delete=models.deletion.DO_NOTHING,
                    to="api.profile",
                ),
            ),
        ],
        options={
            "verbose_name": "App Permission",
            "verbose_name_plural": "App Permissions",
            "db_table": "app_permissions",
            "managed": False,
            "unique_together": {("app_id", "profile")},
        },
    ),

    # -------------------- Sharing --------------------
    migrations.CreateModel(
        name="SharingRecord",
        fields=[
            ("id", models.CharField(max_length=64, primary_key=True, serialize=False)),
            (
                "access_level",
                models.CharField(
                    choices=[
                        ("Private", "Private"),
                        ("Public Read Only", "Public Read Only"),
                        ("Public Read Write", "Public Read Write"),
                    ],
                    max_length=32,
                ),
            ),
            ("created_by_id", models.CharField(blank=True, max_length=64, null=True)),
            ("last_modified_by_id", models.CharField(blank=True, max_length=64, null=True)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("last_modified_date", models.DateTimeField(blank=True, null=True)),
            (
                "object",
                models.ForeignKey(
                    db_column="object_id",
                    db_constraint=False,
                    on_delete=models.deletion.DO_NOTHING,
                    related_name="sharing_records",
                    to="api.platformobject",
                ),
            ),
        ],
        options={
            "verbose_name": "Sharing Record",
            "verbose_name_plural": "Sharing Records",
            "db_table": "sharing_records",
            "managed": False,
            "unique_together": {("object",)},
        },
    ),
    # OrganizationWideDefault model removed — 'owd' has no DDL anywhere
    # in the repo and no runtime queries. Phase 2.A.1 default-deny work
    # uses sharing_records exclusively. Re-add alongside the DDL if/when
    # an OWD feature ships.
]


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0004_add_logo_to_organization"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],          # No DDL — tables already exist.
            state_operations=_STATE_OPERATIONS,
        ),
    ]
