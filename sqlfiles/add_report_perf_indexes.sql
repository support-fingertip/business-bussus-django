-- =====================================================================
-- add_report_perf_indexes.sql
-- =====================================================================
--
-- Purpose
--   Covers the hot filter/join/ORDER BY columns hit by listview and
--   report queries. Every saved report runs at minimum:
--     * 1× details query   (SELECT … FROM t WHERE filters LIMIT N)
--     * 1× summary query   (GROUP BY …, COUNT(id) … on big tables)
--     * 1× count query     (SELECT COUNT(id) … WHERE filters)
--
--   Without indexes on owner_id / is_deleted / created_date / *_id,
--   these all degenerate to sequential scans — which is why a report
--   over a 100 k-row invoice_item table can take multiple seconds per
--   page even after all the query-level optimisations.
--
-- Scope
--   For every table in the public schema, create single-column B-tree
--   indexes on the columns below when they exist and are not already
--   indexed. Safe to re-run; uses IF NOT EXISTS throughout.
--
-- How to run
--   psql -h <host> -U <user> -d <db> -f sqlfiles/add_report_perf_indexes.sql
--
--   For big production tables, prefer the CONCURRENTLY variant at the
--   bottom of this file — it doesn't hold an ACCESS EXCLUSIVE lock but
--   cannot run inside a DO block, so execute each statement one at a
--   time.
-- =====================================================================

-- Columns we want indexed on every object table that has them.
-- owner_id / *_by_id:   report filters "WHERE owner_id = <user>" when the
--                       user is not admin (blcontroller.py:5421) and most
--                       listviews filter by owner or subordinates.
-- is_deleted:           universal soft-delete filter, almost always present
--                       in WHERE clauses.
-- created_date:         default ORDER BY for listviews + reports.
-- last_modified_date:   used by "recently modified" listviews.
-- *_id (FK):            covered separately below by scanning for columns
--                       whose name ends in "_id".

DO $$
DECLARE
    rec        record;
    idx_name   text;
    stmt       text;
    target_col text;
    candidate_cols text[] := ARRAY[
        'owner_id',
        'is_deleted',
        'created_date',
        'last_modified_date',
        'created_by_id',
        'last_modified_by_id'
    ];
BEGIN
    FOREACH target_col IN ARRAY candidate_cols LOOP
        FOR rec IN
            SELECT c.relname AS table_name
            FROM   pg_class       c
            JOIN   pg_namespace   n ON n.oid = c.relnamespace
            JOIN   information_schema.columns col
                   ON col.table_schema = n.nspname
                  AND col.table_name   = c.relname
                  AND col.column_name  = target_col
            WHERE  c.relkind = 'r'
              AND  n.nspname = 'public'
              AND NOT EXISTS (
                    SELECT 1
                    FROM   pg_index i
                    JOIN   pg_attribute a
                           ON a.attrelid = i.indrelid
                          AND a.attnum   = ANY(i.indkey)
                    WHERE  i.indrelid   = c.oid
                      AND  a.attname    = target_col
                      AND  array_length(i.indkey, 1) = 1
              )
        LOOP
            idx_name := 'idx_' || rec.table_name || '_' || target_col;
            stmt := format(
                'CREATE INDEX IF NOT EXISTS %I ON public.%I (%I)',
                idx_name, rec.table_name, target_col
            );
            RAISE NOTICE 'Creating index: %', stmt;
            EXECUTE stmt;
        END LOOP;
    END LOOP;
END
$$;

-- Foreign-key columns: every column whose name ends in "_id" (but isn't the
-- PK "id") gets an index if one doesn't already exist. These drive report
-- JOINs (e.g. invoice_item.invoice_id → invoice.id) and IN-list filters.
DO $$
DECLARE
    rec      record;
    idx_name text;
    stmt     text;
BEGIN
    FOR rec IN
        SELECT c.relname AS table_name, col.column_name
        FROM   pg_class       c
        JOIN   pg_namespace   n ON n.oid = c.relnamespace
        JOIN   information_schema.columns col
               ON col.table_schema = n.nspname
              AND col.table_name   = c.relname
        WHERE  c.relkind = 'r'
          AND  n.nspname = 'public'
          AND  col.column_name LIKE '%\_id' ESCAPE '\'
          AND  col.column_name <> 'id'
          AND NOT EXISTS (
                SELECT 1
                FROM   pg_index i
                JOIN   pg_attribute a
                       ON a.attrelid = i.indrelid
                      AND a.attnum   = ANY(i.indkey)
                WHERE  i.indrelid   = c.oid
                  AND  a.attname    = col.column_name
                  AND  array_length(i.indkey, 1) = 1
          )
    LOOP
        idx_name := 'idx_' || rec.table_name || '_' || rec.column_name;
        -- Postgres identifiers cap at 63 chars; truncate if needed.
        IF length(idx_name) > 63 THEN
            idx_name := substring(idx_name for 63);
        END IF;
        stmt := format(
            'CREATE INDEX IF NOT EXISTS %I ON public.%I (%I)',
            idx_name, rec.table_name, rec.column_name
        );
        RAISE NOTICE 'Creating index: %', stmt;
        EXECUTE stmt;
    END LOOP;
END
$$;

-- Partial index for the "active rows" predicate used by virtually every
-- listview / report: WHERE is_deleted = FALSE. Much smaller than a full
-- index and lets Postgres skip tombstoned rows entirely.
DO $$
DECLARE
    rec      record;
    idx_name text;
    stmt     text;
BEGIN
    FOR rec IN
        SELECT c.relname AS table_name
        FROM   pg_class       c
        JOIN   pg_namespace   n ON n.oid = c.relnamespace
        JOIN   information_schema.columns col
               ON col.table_schema = n.nspname
              AND col.table_name   = c.relname
              AND col.column_name  = 'is_deleted'
        WHERE  c.relkind = 'r'
          AND  n.nspname = 'public'
    LOOP
        idx_name := 'idx_' || rec.table_name || '_active';
        stmt := format(
            'CREATE INDEX IF NOT EXISTS %I ON public.%I (id) WHERE is_deleted = FALSE',
            idx_name, rec.table_name
        );
        RAISE NOTICE 'Creating partial index: %', stmt;
        EXECUTE stmt;
    END LOOP;
END
$$;

-- =====================================================================
-- CONCURRENTLY variant — for production. Generates one CREATE INDEX per
-- missing (table, column) combination; run each row's SQL on its own
-- (cannot be wrapped in a transaction). Copy the output and execute it.
-- =====================================================================
--
-- SELECT format(
--     'CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON public.%I (%I);',
--     substring(('idx_' || c.relname || '_' || col.column_name) for 63),
--     c.relname,
--     col.column_name
-- ) AS stmt
-- FROM pg_class c
-- JOIN pg_namespace n ON n.oid = c.relnamespace
-- JOIN information_schema.columns col
--      ON col.table_schema = n.nspname
--     AND col.table_name   = c.relname
-- WHERE c.relkind = 'r'
--   AND n.nspname = 'public'
--   AND (
--         col.column_name IN (
--             'owner_id', 'is_deleted', 'created_date',
--             'last_modified_date', 'created_by_id', 'last_modified_by_id'
--         )
--         OR (col.column_name LIKE '%\_id' ESCAPE '\' AND col.column_name <> 'id')
--   )
--   AND NOT EXISTS (
--       SELECT 1
--       FROM   pg_index i
--       JOIN   pg_attribute a
--              ON a.attrelid = i.indrelid
--             AND a.attnum   = ANY(i.indkey)
--       WHERE  i.indrelid   = c.oid
--         AND  a.attname    = col.column_name
--         AND  array_length(i.indkey, 1) = 1
--   )
-- ORDER BY c.relname, col.column_name;
