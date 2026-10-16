# Child Welfare Workforce Database (CWW-DB)

An autonomously-maintained, fully-cited database of **workforce** metrics for
every public child welfare agency in the United States — all 51 state-level
jurisdictions today, with county-level rows layered in over time for
county-administered states.

It answers the questions a child welfare workforce expert actually asks:
*How bad is turnover? What's the vacancy rate? How overloaded are caseworkers
vs. the recommended standard? What do they get paid, and what's required to do
the job?* — for each agency, with a source URL and confidence tier on every
number.

## What's here

```
schema/        schema.sql + data_dictionary.md (every metric defined)
data/          agencies.csv (51 jurisdictions) + metrics.csv (the cited observations) ← source of truth
db/            build_db.py builds db/cww.db from the CSVs (deterministic)
agent/         AGENT_PLAYBOOK.md (how the autonomous agent runs) + helper scripts + update_log.md
docs/          DATA_SOURCES.md, EXPANSION_OPTIONS.md (other public data we can add), COVERAGE.md
mirror/        to_notion.py / to_sheets.py (push the repo data to Notion/Sheets for viewing)
(repo root) .github/workflows/cww-refresh.yml (scheduled refresh + always-on validation; path-scoped to this project)
```

## Data model (why it's shaped this way)
A slowly-changing **`agencies`** dimension + a tall/tidy **`metrics`** fact
table (one row per observation). Long form means new measures are added without
schema migrations, and every row carries `source_url`, `period_year`,
`confidence`, and `notes`. See `schema/data_dictionary.md`.

## Quick start
```bash
cd child-welfare-workforce
python db/build_db.py            # validate CSVs + build db/cww.db
python agent/coverage_report.py  # regenerate docs/COVERAGE.md
sqlite3 db/cww.db "SELECT state, value_numeric FROM metrics_latest
                   JOIN agencies USING(agency_id)
                   WHERE metric_key='caseworker_turnover_rate_pct'
                   ORDER BY value_numeric DESC;"
```

## How it stays current ("the agent")
A scheduled GitHub Action (`.github/workflows/cww-refresh.yml`, repo root) runs
weekly. It executes the deterministic collectors + derivations, then an
**OpenAI-powered gatherer** (`agent/openai_refresh.py`, Responses API + web
search) researches the stalest agencies and **proposes cited rows** into
`data/incoming/`, and opens a **draft PR** for review. Prime directive: **never
fabricate; cite everything; missing is left missing.** Nothing enters the
canonical `data/metrics.csv` without passing validation and review.

## Honest limitations (read before using the numbers)
- **No single national workforce feed exists.** State-level vacancy/turnover/
  caseload come from APSRs, audits, court-monitoring reports, and dashboards;
  definitions of "caseworker" vary (investigators vs. ongoing vs. all staff) —
  always read the `notes`.
- **BLS OEWS wages** are a consistent *benchmark occupation* (SOC 21-1021), not
  agency payroll, and several were read from search snippets (bls.gov blocks
  automated fetch) — flagged low/medium pending primary-table verification.
- **Privatized case management** (e.g., KS, NE Eastern, FL CBC lead agencies)
  means some figures describe contractors, not public employees — flagged.
- **Coverage is tiered**: 51 states now (all 51 with data at v0.1); counties are
  being layered in. See `docs/COVERAGE.md` for live gaps.

## Status
v0.1 — see `agent/update_log.md`. Built 2026-06-18 with 414 cited observations
across all 51 jurisdictions.
