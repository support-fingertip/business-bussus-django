-- ============================================================
-- Phase 4.A — canonical DDL for SHARED (public-schema) tables.
-- ============================================================
--
-- Most platform tables are per-tenant (each tenant has its own
-- PostgreSQL schema; DDL in default_tables.sql + tables.sql).
-- A small set of tables are SHARED — they live in the `public`
-- schema and rows are scoped by an `organization_id` column.
-- See `api/ORM/sqlFunctions/getQueryBuilder.py:SHARED_TABLES`
-- for the canonical list.
--
-- This file ships canonical DDL for shared tables that previously
-- had no source-controlled CREATE TABLE block. Operators should
-- apply this file to the public schema once per deployment, AFTER
-- introspecting any existing production table to confirm the
-- column shape matches.
--
-- Tables here are also represented in Django as `managed = False`
-- models (see `api/tenant_models/shared.py`). Django does NOT run
-- DDL for these — operators apply this file by hand.
-- ============================================================

SET search_path TO public;

-- ----------------------------------------------------------
-- lead_capture — Facebook Lead Ads capture configuration.
--
-- Inferred from:
--   * files/fields_inserts_no_id.sql:2206-2284 (field registry —
--     the strongest evidence for the canonical column list)
--   * facebook/leadwebhook.py:159 (runtime SELECT against the
--     table — confirms page_access_token, field_mapping, and
--     created_by_id columns at minimum)
--   * The shared-table convention: organization_id for scoping
--
-- ⚠️  Operator action: before applying this DDL to a production
-- public schema that already has a `lead_capture` table, run
-- `\d lead_capture` and reconcile any drift. If columns differ,
-- update this DDL to match production (the safer direction —
-- the live table is authoritative).
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS lead_capture (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('lCpT_', LEFT(gen_random_uuid()::text, 12)),
    organization_id VARCHAR(64) NOT NULL,
    lead_page_id VARCHAR(255),
    lead_page_name VARCHAR(255),
    lead_form_id VARCHAR(255),
    lead_form_name VARCHAR(255),
    page_access_token TEXT,
    form_status VARCHAR(64),
    field_mapping JSONB,
    task_status VARCHAR(64),
    webhook_url VARCHAR(2048),
    created_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    owner_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for the runtime hot paths:
--   * lookup by lead_form_id (Facebook webhook — facebook/leadwebhook.py:160)
--   * lookup by organization_id (query builder shared-table scoping)
CREATE INDEX IF NOT EXISTS idx_lead_capture_form_id
    ON public.lead_capture (lead_form_id);
CREATE INDEX IF NOT EXISTS idx_lead_capture_organization_id
    ON public.lead_capture (organization_id);
