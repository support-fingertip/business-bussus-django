-- =====================================================================
-- add_fk_parent_name_indexes.sql
-- =====================================================================
--
-- Purpose
--   The FK-lookup cache in createSQLFunction.build_lookup_cache() runs
--     SELECT id::text, name FROM {parent} WHERE id::text = ANY(%s) OR name = ANY(%s)
--   once per import chunk for each parent table.
--
--   Many business tables (accounts, leads, contact, opportunity, campaign,
--   product, ...) declare `name` as NOT NULL but not UNIQUE, so Postgres
--   creates no implicit index. Every chunk then does a sequential scan on
--   the parent, which dominates import time at 100k+ rows.
--
-- What this script does
--   For every table in the public schema that
--     (a) has a column literally named `name`, AND
--     (b) does not already have a single-column index or unique constraint
--         on `name`,
--   create a B-tree index on (name).
--
--   Covers both the hand-written tables in tables.sql and user-defined
--   custom objects created via the Object Manager (so no hand-list needed).
--
-- How to run
--   psql -h <host> -U <user> -d <db> -f sqlfiles/add_fk_parent_name_indexes.sql
--
--   Safe to re-run; each index uses `IF NOT EXISTS`.
--
-- Production note
--   CREATE INDEX takes an ACCESS EXCLUSIVE lock briefly. For large tables
--   (>1M rows) or peak-hours deployment, run the CONCURRENTLY variant at
--   the bottom of this file instead — but it cannot run inside a DO block
--   or a transaction, so you must execute those statements one by one.
-- =====================================================================

-- -------- 1. Diagnostic: list tables that are missing a name index -----
-- Uncomment to inspect before applying. Shows each candidate table with
-- its approximate row count so you can prioritise.
--
-- SELECT  c.relname                     AS table_name,
--         pg_size_pretty(pg_relation_size(c.oid))  AS size,
--         c.reltuples::bigint           AS approx_rows
-- FROM    pg_class       c
-- JOIN    pg_namespace   n ON n.oid = c.relnamespace
-- JOIN    information_schema.columns col
--         ON col.table_schema = n.nspname
--        AND col.table_name   = c.relname
--        AND col.column_name  = 'name'
-- WHERE   c.relkind = 'r'
--   AND   n.nspname = 'public'
--   AND NOT EXISTS (
--         SELECT 1
--         FROM   pg_index i
--         JOIN   pg_attribute a
--                ON a.attrelid = i.indrelid
--               AND a.attnum   = ANY(i.indkey)
--         WHERE  i.indrelid   = c.oid
--           AND  a.attname    = 'name'
--           AND  array_length(i.indkey, 1) = 1   -- single-column index only
--   )
-- ORDER BY c.reltuples DESC;

-- -------- 2. Apply: create missing indexes -----------------------------
DO $$
DECLARE
    rec        record;
    idx_name   text;
    stmt       text;
BEGIN
    FOR rec IN
        SELECT  c.relname AS table_name
        FROM    pg_class       c
        JOIN    pg_namespace   n ON n.oid = c.relnamespace
        JOIN    information_schema.columns col
                ON col.table_schema = n.nspname
               AND col.table_name   = c.relname
               AND col.column_name  = 'name'
        WHERE   c.relkind = 'r'
          AND   n.nspname = 'public'
          AND NOT EXISTS (
                SELECT 1
                FROM   pg_index i
                JOIN   pg_attribute a
                       ON a.attrelid = i.indrelid
                      AND a.attnum   = ANY(i.indkey)
                WHERE  i.indrelid   = c.oid
                  AND  a.attname    = 'name'
                  AND  array_length(i.indkey, 1) = 1
          )
    LOOP
        idx_name := 'idx_' || rec.table_name || '_name';
        stmt := format(
            'CREATE INDEX IF NOT EXISTS %I ON public.%I (name)',
            idx_name, rec.table_name
        );
        RAISE NOTICE 'Creating index: %', stmt;
        EXECUTE stmt;
    END LOOP;
END
$$;

-- -------- 3. CONCURRENTLY variant (run one at a time, outside txn) -----
-- For large production tables, generate the per-table statements with
-- this query, copy them out, and run each one on its own line.
--
-- SELECT  format(
--             'CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON public.%I (name);',
--             'idx_' || c.relname || '_name',
--             c.relname
--         ) AS stmt
-- FROM    pg_class       c
-- JOIN    pg_namespace   n ON n.oid = c.relnamespace
-- JOIN    information_schema.columns col
--         ON col.table_schema = n.nspname
--        AND col.table_name   = c.relname
--        AND col.column_name  = 'name'
-- WHERE   c.relkind = 'r'
--   AND   n.nspname = 'public'
--   AND NOT EXISTS (
--         SELECT 1
--         FROM   pg_index i
--         JOIN   pg_attribute a
--                ON a.attrelid = i.indrelid
--               AND a.attnum   = ANY(i.indkey)
--         WHERE  i.indrelid   = c.oid
--           AND  a.attname    = 'name'
--           AND  array_length(i.indkey, 1) = 1
--   )
-- ORDER BY c.relname;
