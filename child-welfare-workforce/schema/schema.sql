-- Child Welfare Workforce Database (CWW-DB)
-- SQLite schema. Source of truth lives in the versioned CSVs under /data;
-- this schema defines the database that db/build_db.py assembles from them.
--
-- Design notes
-- ------------
-- * Two-table star: a slowly-changing `agencies` dimension and a tall/tidy
--   `metrics` fact table. Storing metrics in long form (one row per
--   observation) means new measures can be added over time WITHOUT schema
--   migrations -- critical for a database meant to be improved on a routine
--   basis.
-- * Every metric value carries full provenance: the source name, URL,
--   publication date, the year the data describes, and a confidence tier.
--   Nothing enters the database without a citation.
-- * `sources` is an optional normalized catalog; metrics also embed the
--   source inline so a single CSV is self-describing.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Dimension: agencies (one row per public child welfare agency)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agencies (
    agency_id          TEXT PRIMARY KEY,         -- e.g. 'US-CA' (state) or 'US-CA-Los_Angeles' (county)
    jurisdiction_level TEXT NOT NULL,            -- 'state' | 'county'
    state              TEXT NOT NULL,            -- USPS 2-letter code
    county             TEXT,                     -- NULL for state-level rows
    fips               TEXT,                     -- state or county FIPS code
    agency_name        TEXT,                     -- official agency name
    agency_url         TEXT,                     -- primary public URL
    admin_structure    TEXT,                     -- 'state-administered' | 'county-administered' | 'state-supervised-county-administered' | 'hybrid'
    population          INTEGER,                  -- jurisdiction population (context/denominator)
    notes              TEXT,
    CHECK (jurisdiction_level IN ('state','county'))
);

-- ---------------------------------------------------------------------------
-- Fact: metrics (one row per observed value, fully cited)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS metrics (
    id              INTEGER PRIMARY KEY,
    agency_id       TEXT NOT NULL REFERENCES agencies(agency_id),
    metric_key      TEXT NOT NULL,               -- controlled vocabulary; see data_dictionary.md
    value_numeric   REAL,                         -- populated for numeric metrics
    value_text      TEXT,                         -- populated for categorical/text metrics
    unit            TEXT,                         -- 'pct'|'count'|'ratio'|'usd'|'years'|'days'|'hours' or NULL
    period_year     INTEGER,                      -- year the data describes
    as_of_date      TEXT,                         -- ISO date if a precise point-in-time is given
    source_name     TEXT,
    source_url      TEXT,
    source_pub_date TEXT,
    confidence      TEXT,                         -- 'high'|'medium'|'low'
    notes           TEXT,
    collected_at    TEXT,                         -- ISO timestamp the agent recorded this row
    CHECK (confidence IN ('high','medium','low') OR confidence IS NULL),
    CHECK (value_numeric IS NOT NULL OR value_text IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_metrics_agency  ON metrics(agency_id);
CREATE INDEX IF NOT EXISTS idx_metrics_key     ON metrics(metric_key);
CREATE INDEX IF NOT EXISTS idx_metrics_year    ON metrics(period_year);

-- ---------------------------------------------------------------------------
-- Optional normalized source catalog
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sources (
    source_id    TEXT PRIMARY KEY,
    name         TEXT,
    owner        TEXT,
    url          TEXT,
    granularity  TEXT,   -- 'national'|'state'|'county'
    cadence      TEXT,   -- 'annual'|'quarterly'|'ad hoc' etc.
    access       TEXT,   -- 'api'|'download'|'dashboard'|'pdf'
    notes        TEXT
);

-- ---------------------------------------------------------------------------
-- Convenience view: latest value of each metric per agency
-- ---------------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS metrics_latest AS
SELECT m.*
FROM metrics m
JOIN (
    SELECT agency_id, metric_key, MAX(COALESCE(period_year, 0)) AS max_year
    FROM metrics
    GROUP BY agency_id, metric_key
) latest
  ON m.agency_id = latest.agency_id
 AND m.metric_key = latest.metric_key
 AND COALESCE(m.period_year, 0) = latest.max_year;
