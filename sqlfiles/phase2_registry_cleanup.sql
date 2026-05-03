-- Phase 2 ORM Wave 2 — registry cleanup migration.
--
-- Apply once per tenant schema after deploying the new
-- objects.sql seed. Idempotent: each operation is a no-op
-- if already applied.
--
-- Operator usage:
--   SET search_path TO <tenant_schema>;
--   \i sqlfiles/phase2_registry_cleanup.sql

BEGIN;

-- (1) Drop vestigial registry rows.
DELETE FROM object WHERE name IN ('apex_class', 'approval_processes', 'audit_trails', 'auth_group', 'auth_group_permissions', 'auth_permission', 'call_logs', 'columns_metadata', 'component', 'connected_app', 'custom_metadata', 'custom_setting', 'customers', 'duplicate_rule', 'flows', 'group_assignment_tracker', 'hsitory', 'import_wizard', 'invoice_items', 'invoices', 'lightning_pages', 'matching_rule', 'named_credential', 'node', 'owd', 'package', 'permission_sets', 'process_builders', 'products', 'regions', 'remote_site_setting', 'roles', 'sales', 'setup', 'sf_integration_lead', 'sharing_rules', 'tables_metadata', 'tabs', 'theme', 'users_user_permissions', 'workflow_rules');

-- (2) Rename 'reports' → 'report' so the registry name matches
--     the actual table created by default_tables.sql.
UPDATE object SET name = 'report', label = 'Report', plural_label = 'Reports' WHERE name = 'reports';

-- (3) Insert missing setup-table registry rows.
INSERT INTO object (name, label, plural_label, type, setup) VALUES ('callactivity', 'Call Activity', 'Call Activities', 'standard', TRUE) ON CONFLICT DO NOTHING;
INSERT INTO object (name, label, plural_label, type, setup) VALUES ('dashboard_assignment', 'Dashboard Assignment', 'Dashboard Assignments', 'standard', TRUE) ON CONFLICT DO NOTHING;
INSERT INTO object (name, label, plural_label, type, setup) VALUES ('dashboard_component', 'Dashboard Component', 'Dashboard Components', 'standard', TRUE) ON CONFLICT DO NOTHING;
INSERT INTO object (name, label, plural_label, type, setup) VALUES ('dashboard_folder_sharing', 'Dashboard Folder Sharing', 'Dashboard Folder Sharings', 'standard', TRUE) ON CONFLICT DO NOTHING;
INSERT INTO object (name, label, plural_label, type, setup) VALUES ('dashboard_folders', 'Dashboard Folders', 'Dashboard Folders', 'standard', TRUE) ON CONFLICT DO NOTHING;
INSERT INTO object (name, label, plural_label, type, setup) VALUES ('email_provider_setup', 'Email Provider Setup', 'Email Provider Setups', 'standard', TRUE) ON CONFLICT DO NOTHING;
INSERT INTO object (name, label, plural_label, type, setup) VALUES ('field_mapping', 'Field Mapping', 'Field Mappings', 'standard', TRUE) ON CONFLICT DO NOTHING;
INSERT INTO object (name, label, plural_label, type, setup) VALUES ('homepage_assignment', 'Homepage Assignment', 'Homepage Assignments', 'standard', TRUE) ON CONFLICT DO NOTHING;
INSERT INTO object (name, label, plural_label, type, setup) VALUES ('notifications', 'Notifications', 'Notifications', 'standard', TRUE) ON CONFLICT DO NOTHING;
INSERT INTO object (name, label, plural_label, type, setup) VALUES ('org_company', 'Organization Company', 'Organization Companies', 'standard', TRUE) ON CONFLICT DO NOTHING;
INSERT INTO object (name, label, plural_label, type, setup) VALUES ('organizations', 'Organizations', 'Organizations', 'standard', TRUE) ON CONFLICT DO NOTHING;
INSERT INTO object (name, label, plural_label, type, setup) VALUES ('page_builder', 'Page Builder', 'Page Builders', 'standard', TRUE) ON CONFLICT DO NOTHING;
INSERT INTO object (name, label, plural_label, type, setup) VALUES ('page_component', 'Page Component', 'Page Components', 'standard', TRUE) ON CONFLICT DO NOTHING;
INSERT INTO object (name, label, plural_label, type, setup) VALUES ('report_folder', 'Report Folder', 'Report Folders', 'standard', TRUE) ON CONFLICT DO NOTHING;
INSERT INTO object (name, label, plural_label, type, setup) VALUES ('report_folder_sharing', 'Report Folder Sharing', 'Report Folder Sharings', 'standard', TRUE) ON CONFLICT DO NOTHING;
INSERT INTO object (name, label, plural_label, type, setup) VALUES ('shared_records', 'Shared Records (per-record)', 'Shared Records (per-record)', 'standard', TRUE) ON CONFLICT DO NOTHING;
INSERT INTO object (name, label, plural_label, type, setup) VALUES ('telephony_user', 'Telephony User', 'Telephony Users', 'standard', TRUE) ON CONFLICT DO NOTHING;
INSERT INTO object (name, label, plural_label, type, setup) VALUES ('user_gmail_tokens', 'User Gmail Tokens', 'User Gmail Tokens', 'standard', TRUE) ON CONFLICT DO NOTHING;
INSERT INTO object (name, label, plural_label, type, setup) VALUES ('user_group_profiles', 'User Group Profiles', 'User Group Profiles', 'standard', TRUE) ON CONFLICT DO NOTHING;
INSERT INTO object (name, label, plural_label, type, setup) VALUES ('user_group_public_groups', 'User Group Public Groups', 'User Group Public Groups', 'standard', TRUE) ON CONFLICT DO NOTHING;
INSERT INTO object (name, label, plural_label, type, setup) VALUES ('user_outlook_tokens', 'User Outlook Tokens', 'User Outlook Tokens', 'standard', TRUE) ON CONFLICT DO NOTHING;

-- (4) Insert missing business-object registry rows.
INSERT INTO object (name, label, plural_label, type, setup) VALUES ('activity', 'Activity', 'Activities', 'standard', FALSE) ON CONFLICT DO NOTHING;
INSERT INTO object (name, label, plural_label, type, setup) VALUES ('email', 'Email Record', 'Email Records', 'standard', FALSE) ON CONFLICT DO NOTHING;

COMMIT;
