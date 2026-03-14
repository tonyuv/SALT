CREATE TABLE IF NOT EXISTS telemetry_readings (
    id BIGSERIAL PRIMARY KEY,
    sensor_id VARCHAR(64) NOT NULL,
    vin VARCHAR(24) NOT NULL,
    manufacturer VARCHAR(32),
    vehicle VARCHAR(64),
    value DOUBLE PRECISION NOT NULL,
    unit VARCHAR(16) NOT NULL,
    label VARCHAR(32) NOT NULL,
    kafka_topic VARCHAR(64) NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_telemetry_vin ON telemetry_readings (vin);
CREATE INDEX idx_telemetry_label ON telemetry_readings (label);
CREATE INDEX idx_telemetry_ts ON telemetry_readings (ts DESC);
CREATE INDEX idx_telemetry_manufacturer ON telemetry_readings (manufacturer);

CREATE TABLE IF NOT EXISTS connection_events (
    id BIGSERIAL PRIMARY KEY,
    sensor_id VARCHAR(64) NOT NULL,
    vin VARCHAR(24) NOT NULL,
    manufacturer VARCHAR(32),
    vehicle VARCHAR(64),
    label VARCHAR(32),
    event VARCHAR(16) NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_conn_vin ON connection_events (vin);
CREATE INDEX idx_conn_event ON connection_events (event);

CREATE TABLE IF NOT EXISTS agent_logs (
    id BIGSERIAL PRIMARY KEY,
    level VARCHAR(16) NOT NULL,
    component VARCHAR(32) NOT NULL,
    message TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_agent_level ON agent_logs (level);
