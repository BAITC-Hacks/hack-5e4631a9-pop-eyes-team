\set ON_ERROR_STOP on

-- Atomic and repeatable: invalid input rolls back the entire import.
BEGIN;

CREATE TEMP TABLE csv_contractors (
    id TEXT PRIMARY KEY,
    anon_name TEXT,
    categories TEXT,
    city TEXT,
    city_imputed BOOLEAN,
    synthetic BOOLEAN,
    price_from_kzt BIGINT,
    price_imputed BOOLEAN,
    event_formats TEXT,
    languages TEXT,
    max_hours NUMERIC(6, 2),
    busy_dates TEXT,
    description TEXT
) ON COMMIT DROP;

COPY csv_contractors FROM '/seed/contractors.csv'
    WITH (FORMAT csv, HEADER MATCH, ENCODING 'UTF8');

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM csv_contractors) THEN
        RAISE EXCEPTION 'The contractor CSV is empty; refusing to import';
    END IF;
    IF EXISTS (
        SELECT 1 FROM csv_contractors,
        LATERAL unnest(string_to_array(busy_dates, '|')::DATE[]) AS busy(day)
        WHERE busy.day < DATE '2026-09-23' OR busy.day > DATE '2026-12-31'
    ) THEN
        RAISE EXCEPTION 'Busy dates are outside the declared dataset calendar';
    END IF;
END
$$;

INSERT INTO contractors (
    id, anon_name, categories, city, city_imputed, synthetic, price_from_kzt,
    price_imputed, event_formats, languages, max_hours, busy_dates, description
)
SELECT
    id, anon_name, string_to_array(categories, '|'), city, city_imputed,
    synthetic, price_from_kzt, price_imputed,
    string_to_array(event_formats, '|'), string_to_array(languages, '|'),
    max_hours, COALESCE(string_to_array(busy_dates, '|')::DATE[], '{}'::DATE[]),
    description
FROM csv_contractors
ON CONFLICT (id) DO UPDATE SET
    anon_name = EXCLUDED.anon_name,
    categories = EXCLUDED.categories,
    city = EXCLUDED.city,
    city_imputed = EXCLUDED.city_imputed,
    synthetic = EXCLUDED.synthetic,
    price_from_kzt = EXCLUDED.price_from_kzt,
    price_imputed = EXCLUDED.price_imputed,
    event_formats = EXCLUDED.event_formats,
    languages = EXCLUDED.languages,
    max_hours = EXCLUDED.max_hours,
    busy_dates = EXCLUDED.busy_dates,
    description = EXCLUDED.description;

-- Version the actual catalog, independently of the import timestamp.
INSERT INTO dataset_metadata (
    singleton, source_file, source_sha256, dataset_version, profile_count,
    calendar_start, calendar_end, imported_at
)
SELECT
    TRUE,
    'hackathon dataset anonymized .csv',
    encode(sha256(pg_read_binary_file('/seed/contractors.csv')), 'hex'),
    encode(sha256(convert_to(jsonb_agg(to_jsonb(c) ORDER BY c.id)::TEXT, 'UTF8')), 'hex'),
    count(*)::INTEGER,
    DATE '2026-09-23', DATE '2026-12-31', now()
FROM contractors c
ON CONFLICT (singleton) DO UPDATE SET
    source_file = EXCLUDED.source_file,
    source_sha256 = EXCLUDED.source_sha256,
    dataset_version = EXCLUDED.dataset_version,
    profile_count = EXCLUDED.profile_count,
    calendar_start = EXCLUDED.calendar_start,
    calendar_end = EXCLUDED.calendar_end,
    imported_at = EXCLUDED.imported_at;

COMMIT;
