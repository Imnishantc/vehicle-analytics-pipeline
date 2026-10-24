-- Vehicle analytics schema (PostgreSQL 13+). Idempotent: safe to run repeatedly.

CREATE TABLE IF NOT EXISTS streams (
    stream_id   TEXT PRIMARY KEY,
    rtsp_url    TEXT,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per line-crossing "count" event emitted by the DeepStream probe.
CREATE TABLE IF NOT EXISTS crossing_events (
    id               BIGSERIAL PRIMARY KEY,
    stream_id        TEXT        NOT NULL REFERENCES streams (stream_id),
    pipeline_run_id  UUID        NOT NULL,           -- tracker IDs are only unique within a run
    vehicle_id       BIGINT      NOT NULL,           -- nvtracker object_id
    vehicle_class    TEXT        NOT NULL,           -- detector label (e.g. Car)
    class_confidence REAL,
    color            TEXT,                           -- secondary classifier label
    color_confidence REAL,
    direction        TEXT        NOT NULL CHECK (direction IN ('in', 'out')),
    line_id          TEXT        NOT NULL DEFAULT 'line-1',
    event_time       TIMESTAMPTZ NOT NULL,           -- UTC wall-clock at crossing
    frame_number     BIGINT,
    bbox_left        REAL,
    bbox_top         REAL,
    bbox_width       REAL,
    bbox_height      REAL,
    source           TEXT        NOT NULL DEFAULT 'deepstream',  -- 'test' for fixtures
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Duplicate protection: a track counts once per line per direction per run.
    CONSTRAINT uq_crossing_once UNIQUE (pipeline_run_id, stream_id, line_id, vehicle_id, direction)
);

CREATE INDEX IF NOT EXISTS idx_events_time        ON crossing_events (event_time DESC);
CREATE INDEX IF NOT EXISTS idx_events_stream_time ON crossing_events (stream_id, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_events_color       ON crossing_events (color);
CREATE INDEX IF NOT EXISTS idx_events_class       ON crossing_events (vehicle_class);

-- Liveness signal written by the DeepStream event worker (used by /api/streams/status).
CREATE TABLE IF NOT EXISTS pipeline_heartbeats (
    stream_id     TEXT PRIMARY KEY REFERENCES streams (stream_id),
    pipeline_run_id UUID,
    state         TEXT        NOT NULL DEFAULT 'unknown',
    fps           REAL,
    frames        BIGINT,
    last_frame_at TIMESTAMPTZ,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    detail        TEXT
);
