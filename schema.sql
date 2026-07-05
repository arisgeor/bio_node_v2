-- ============================================================================
-- BioNode V2.1 -- SQLite logging schema
-- ============================================================================
-- Conventions:
--   * ALL timestamps are UTC, ISO-8601 text: 'YYYY-MM-DD HH:MM:SS' (UTC).
--     Store UTC, display local. Never store local time.
--   * One DB file per node is fine; mission / session / node IDs disambiguate.
--   * After creating the DB, enable WAL once:   PRAGMA journal_mode=WAL;
--     (WAL + append-only writes = a power-loss / reboot on the move costs a few
--      seconds of data, not the dataset -- this is your swap-reboot insurance.)
--
-- Sensor role reminder (do NOT blur these):
--   SCD30    -> co2_ppm + scd30_temp_c / scd30_rh_pct   (primary CO2 & T/RH)
--   BME280   -> bme280_*  (pressure + T/RH CROSS-CHECK only)
--   SGP30    -> tvoc_ppb (real) + eco2_proxy_ppm (PROXY -- never a real CO2 value)
--   BH1750   -> lux
--   MAX30102 -> heart_rate_bpm / spo2_pct
--   MLX90614 -> surface_temp_c (object) [+ ambient optional]
-- ============================================================================

PRAGMA foreign_keys = ON;

-- One row per deployment / analog mission ------------------------------------
CREATE TABLE IF NOT EXISTS missions (
    mission_id  INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,            -- e.g. 'AAT-112'
    node_id     TEXT NOT NULL,            -- e.g. 'bionode-01'
    site        TEXT,                     -- e.g. 'AATC/LunAres, Pila'
    altitude_m  REAL,                     -- ~70
    start_utc   TEXT NOT NULL,            -- UTC ISO-8601
    end_utc     TEXT,
    notes       TEXT
);

-- A continuous logging run. The soak test is a session; each deployment
-- context / restart can open a new session. ---------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    session_id              INTEGER PRIMARY KEY,
    mission_id              INTEGER NOT NULL REFERENCES missions(mission_id),
    subject_id              TEXT,                          -- n=1 -> e.g. 'aris'
    start_utc               TEXT NOT NULL,
    end_utc                 TEXT,
    sample_interval_seconds INTEGER NOT NULL DEFAULT 2,    -- nominal (2 active / 10 rest)
    notes                   TEXT
);

-- The time series ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS readings (
    reading_id       INTEGER PRIMARY KEY,
    session_id       INTEGER NOT NULL REFERENCES sessions(session_id),
    timestamp_utc    TEXT NOT NULL,                        -- UTC ISO-8601
    mission_day      INTEGER,                              -- 0,1,2... derived at insert
    activity_context TEXT NOT NULL DEFAULT 'unspecified'
        CHECK (activity_context IN
            ('sleep','eva','exercise','teamwork','meal','rest','work','unspecified')),
    location_tag     TEXT,                                 -- NULL = chamber; set when roving

    -- CO2 (SCD30, primary)
    co2_ppm             REAL,
    -- SCD30 onboard T/RH (primary)
    scd30_temp_c        REAL,
    scd30_rh_pct        REAL,
    -- BME280 (cross-check only)
    bme280_temp_c       REAL,
    bme280_rh_pct       REAL,
    bme280_pressure_hpa REAL,
    -- SGP30 (TVOC real; eCO2 is a PROXY)
    tvoc_ppb            REAL,
    eco2_proxy_ppm      REAL,
    -- BH1750
    lux                 REAL,
    -- MAX30102
    heart_rate_bpm      REAL,
    spo2_pct            REAL,
    -- MLX90614
    surface_temp_c      REAL,                              -- object temperature
    mlx_ambient_c       REAL                               -- optional; sensor's ambient
);

-- Button marks, location / activity changes, and power / restart markers -----
CREATE TABLE IF NOT EXISTS events (
    event_id      INTEGER PRIMARY KEY,
    session_id    INTEGER NOT NULL REFERENCES sessions(session_id),
    timestamp_utc TEXT NOT NULL,
    event_type    TEXT NOT NULL DEFAULT 'marker'
        CHECK (event_type IN
            ('marker','location_change','activity_change','power_restart','note')),
    label         TEXT,                                    -- e.g. 'mark 4', 'gym', 'sleep'
    notes         TEXT
);

-- Indexes for the queries you'll actually run --------------------------------
CREATE INDEX IF NOT EXISTS idx_readings_session_time ON readings(session_id, timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_events_session_time   ON events(session_id, timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_readings_activity     ON readings(session_id, activity_context);
