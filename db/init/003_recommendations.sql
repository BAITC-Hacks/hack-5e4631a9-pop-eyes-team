\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS recommendation_results (
    request_key TEXT PRIMARY KEY,
    request_payload JSONB NOT NULL,
    dataset_version TEXT NOT NULL,
    recommendation_version TEXT NOT NULL,
    response JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE recommendation_results IS
    'First validated response per normalized request and data/ranking versions; preserves card order.';

COMMIT;
