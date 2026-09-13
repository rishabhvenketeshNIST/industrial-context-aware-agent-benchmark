-- NOTE: this file is the schema for a FRESH deployment. Against an
-- existing deployment you want to keep (e.g. accumulated experiment
-- history), do not re-run this file -- it drops the table. Apply the
-- generation_id addition non-destructively instead:
--   ALTER TABLE observations ADD COLUMN IF NOT EXISTS generation_id TEXT;

DROP TABLE IF EXISTS observations CASCADE;

CREATE TABLE observations (
    observation_id TEXT NOT NULL,
    measurement_id TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    value DOUBLE PRECISION,
    unit TEXT,
    quality TEXT,
    source TEXT,
    source_id TEXT,
    -- Which icab.scenarios.runner.ScenarioRunner preparation wrote this row
    -- (NULL for data written outside that path, e.g. the legacy static
    -- prototype loader). Distinguishes this run's own data from other
    -- runs' accumulation in this shared historian; see
    -- docs/research/experiment-plan.md.
    generation_id TEXT,

    PRIMARY KEY (observation_id, timestamp)
);

SELECT create_hypertable(
    'observations',
    'timestamp',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_observations_measurement_time
    ON observations (measurement_id, timestamp DESC);