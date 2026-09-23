\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS contractors (
    id TEXT PRIMARY KEY CHECK (length(btrim(id)) > 0),
    anon_name TEXT NOT NULL CHECK (length(btrim(anon_name)) > 0),
    categories TEXT[] NOT NULL CHECK (cardinality(categories) > 0),
    city TEXT NOT NULL CHECK (length(btrim(city)) > 0),
    city_imputed BOOLEAN NOT NULL,
    synthetic BOOLEAN NOT NULL,
    price_from_kzt BIGINT NOT NULL CHECK (price_from_kzt >= 0),
    price_imputed BOOLEAN NOT NULL,
    event_formats TEXT[] NOT NULL CHECK (cardinality(event_formats) > 0),
    languages TEXT[] NOT NULL CHECK (cardinality(languages) > 0),
    max_hours NUMERIC(6, 2) CHECK (max_hours > 0),
    busy_dates DATE[] NOT NULL DEFAULT '{}',
    description TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS contractors_city_price_idx
    ON contractors (city, price_from_kzt);
CREATE INDEX IF NOT EXISTS contractors_categories_idx
    ON contractors USING GIN (categories);

CREATE TABLE IF NOT EXISTS dataset_metadata (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    source_file TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    profile_count INTEGER NOT NULL CHECK (profile_count > 0),
    calendar_start DATE NOT NULL,
    calendar_end DATE NOT NULL CHECK (calendar_end >= calendar_start),
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON COLUMN contractors.price_from_kzt IS
    'Starting price per event in KZT, not a final quote.';
COMMENT ON COLUMN contractors.max_hours IS
    'NULL means on-site duration is not applicable, not zero hours.';
COMMENT ON COLUMN contractors.busy_dates IS
    'Availability is known only inside the dataset_metadata calendar window.';

COMMIT;
