-- 0001_init.sql
-- Survey codebook generator: core schema.
-- One source of truth for AVA Lab helper files. SQLite, single-writer.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS surveys (
    survey_id      TEXT PRIMARY KEY,            -- internal slug or Qualtrics SV_*
    qualtrics_id   TEXT,                        -- SV_* when ingested via API
    title          TEXT NOT NULL,
    owner          TEXT,
    first_seen_at  TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_surveys_qualtrics_id ON surveys(qualtrics_id);
CREATE INDEX IF NOT EXISTS idx_surveys_title         ON surveys(title COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    survey_id         TEXT NOT NULL REFERENCES surveys(survey_id),
    source            TEXT NOT NULL CHECK (source IN ('qualtrics','pdf','docx','url','notion-seed','manual')),
    source_uri        TEXT,
    started_at        TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at       TEXT,
    parser_version    TEXT,
    claude_model      TEXT,
    status            TEXT NOT NULL DEFAULT 'running'
                      CHECK (status IN ('running','complete','failed','cancelled')),
    n_variables       INTEGER NOT NULL DEFAULT 0,
    notes             TEXT,
    triggered_by      TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_survey ON ingestion_runs(survey_id, started_at DESC);

CREATE TABLE IF NOT EXISTS instruments (
    instrument_id  TEXT PRIMARY KEY,            -- canonical short id (e.g. AWE_MICA_POST)
    survey_id      TEXT NOT NULL REFERENCES surveys(survey_id),
    name           TEXT NOT NULL,
    role           TEXT,                        -- pre / post / followup / satisfaction / etc.
    language       TEXT DEFAULT 'en',
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_instruments_survey ON instruments(survey_id);

CREATE TABLE IF NOT EXISTS variables (
    variable_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ingestion_run_id     INTEGER NOT NULL REFERENCES ingestion_runs(id),
    survey_id            TEXT NOT NULL REFERENCES surveys(survey_id),
    instrument_id        TEXT REFERENCES instruments(instrument_id),
    variable_name        TEXT NOT NULL,         -- canonical short name (q_engage_1)
    label                TEXT,                  -- full item text as presented
    question_text        TEXT,                  -- prompt only (e.g. "On a scale of 1-5...")
    variable_type        TEXT,                  -- Likert / Multiple Choice / Free Text / Numeric / Date / Composite / Derived / Demographic / Unknown
    domain               TEXT,                  -- comma-separated for now: Quality Rating, Knowledge, Climate, ...
    dimension            TEXT,                  -- finer grouping (Group Cohesion, Team Climate, ...)
    scale                TEXT,                  -- JSON or short text describing response scale
    reverse_scored       INTEGER NOT NULL DEFAULT 0,
    derivation_logic     TEXT,                  -- e.g. "mean of Q1-Q5; reverse Q3"
    source_instrument    TEXT,
    cours                TEXT,                  -- AVAL training-code column (e.g. P11_DT_OV_CO_SD_Survey123)
    notes                TEXT,
    flag                 TEXT,                  -- "Needs Rob Review" | "Confirmed"
    position             INTEGER,               -- ordering within the instrument
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_variables_run     ON variables(ingestion_run_id);
CREATE INDEX IF NOT EXISTS idx_variables_survey  ON variables(survey_id);
CREATE INDEX IF NOT EXISTS idx_variables_name    ON variables(variable_name);

CREATE TABLE IF NOT EXISTS response_options (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    variable_id     INTEGER NOT NULL REFERENCES variables(variable_id) ON DELETE CASCADE,
    value_numeric   REAL,
    value_text      TEXT NOT NULL,
    order_index     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_options_variable ON response_options(variable_id, order_index);

CREATE TABLE IF NOT EXISTS api_keys (
    key_hash      TEXT PRIMARY KEY,             -- sha256 of the raw key
    user_email    TEXT NOT NULL,
    label         TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    last_used_at  TEXT,
    revoked_at    TEXT
);

INSERT OR IGNORE INTO schema_migrations(version) VALUES ('0001_init');
