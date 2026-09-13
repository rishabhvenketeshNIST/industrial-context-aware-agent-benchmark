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

    PRIMARY KEY (observation_id, timestamp)
);

SELECT create_hypertable(
    'observations',
    'timestamp',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_observations_measurement_time
    ON observations (measurement_id, timestamp DESC);