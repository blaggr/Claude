# Plan: Survey Codebook Generator (RFS Helper File Builder)

**Status:** draft for AVAL team review
**Branch:** `claude/survey-codebook-generator-eTLnp`
**Author:** Rob Blagg (with Claude)
**Last updated:** 2026-05-16

## Goal

Given a Qualtrics survey ID, title, public link, PDF, or Word doc, automatically
produce a helper file in the "Internal Helper Columns" layout, land it in the
existing **AWE Evaluation Database** (Notion: Trainings/Instruments/Variables/
Datasets), mirror to a SQLite DB on Box for direct Alteryx ODBC access, and
expose a small REST API so any AVAL teammate can pull variables by survey ID or
name.

## Confirmed scope (from intake Q&A)

| Decision | Choice |
|---|---|
| Helper file location | Existing Notion **AWE Evaluation Database** (extend, don't fork) |
| Database engine | **SQLite** mounted on Box |
| Hosting | Lightweight FastAPI on a lab workstation, DB file on Box |
| Alteryx access | Direct DB connection (ODBC/SQL) primary; REST API secondary |
| Ingest sources | Qualtrics API primary; PDF / DOCX fallback |
| Auth | API keys per user (header `X-API-Key`) |
| Versioning | Every ingestion creates a new version row; old helpers stay queryable |
| Output column layout | Modern "Internal Helper Columns" (+ legacy view for back-compat) |

## Architecture — one source of truth, two consumer surfaces

```
                                ┌──────────────────────────────┐
                                │ Existing AWE Notion DBs      │
                                │  Trainings · Instruments     │
                                │  Variables · Datasets        │
                                └──────────────▲───────────────┘
                                               │ (Notion API, canonical metadata)
┌──────────────────┐   ┌────────────────┐      │
│ Streamlit app    │──►│  Ingestion     │──────┤
│ (existing /app)  │   │  pipeline      │      │
│  + new tab:      │   │   Qualtrics    │      │
│  "Build helper"  │   │   PDF / DOCX   │      │
└──────────────────┘   │   Claude-based │      │
                       │   normalizer   │      │
                       └────────┬───────┘      │
                                ▼              ▼
                       ┌────────────────────────────────────┐
                       │ codebook.sqlite  (on Box)          │
                       │  ingestion_runs   (versions)       │
                       │  surveys · instruments             │
                       │  variables  (modern long schema)   │
                       │  response_options                  │
                       │  v_helper_modern  (Alteryx view)   │
                       │  v_helper_legacy  (Alteryx view)   │
                       └────────────────┬───────────────────┘
                                        │
              ┌─────────────────────────┼────────────────────────┐
              ▼                         ▼                        ▼
    Alteryx Input Data            FastAPI service         curl / Python
    (SQLite ODBC →                /helper /variables      (API-key)
     v_helper_modern)             /ingest  /runs
```

## Components

### 1. Storage — `codebook.sqlite` on Box

Why SQLite-on-Box: zero infra, sits alongside `RFS Files/`, replicates to the
team's machines, Alteryx reads it via the SQLite ODBC driver. The API server is
the **sole writer** (avoids Box concurrent-write hazards); analysts get
read-only ODBC.

Tables:

- `ingestion_runs(id, survey_id, source, source_uri, started_at, finished_at,
  parser_version, claude_model, status, n_variables, notes)` — one row per
  pull, this is your version history
- `surveys(survey_id, qualtrics_id, title, owner, last_seen_at)`
- `instruments(instrument_id, survey_id, name, role, language)` — mirrors
  Notion Instruments
- `variables(variable_id, ingestion_run_id, survey_id, instrument_id,
  variable_name, label, question_text, variable_type, domain, dimension, scale,
  reverse_scored, derivation_logic, source_instrument, cours, notes, flag,
  position)` — mirrors Notion Variables, adds `cours` for the COURS column your
  team uses
- `response_options(variable_id, value_numeric, value_text, order_index)`
- View `v_helper_modern` — latest run per survey, Internal Helper Columns
  layout
- View `v_helper_legacy` — flattened to
  `Class / Timestamp / Dimension / Name / Value_Numeric / Value_Text` so
  today's Alteryx workflow keeps working unchanged

### 2. Ingestion pipeline (`codebook_builder/`)

| Source | Strategy |
|---|---|
| Qualtrics survey ID | Reuse `qualtrics-awe-analysis` skill's `pull_qualtrics.py`; hit the Survey Definition API for question metadata + choices + display logic |
| Survey title | List-surveys + fuzzy title match (warn on ambiguity, never auto-pick) |
| Public link (.qsf, share-PDF) | Sniff content-type, route to the matching parser |
| PDF / DOCX | `pdfplumber` / `python-docx` to extract question blocks |

Single normalizer `normalize.py` calls **Claude (claude-opus-4-7)** with
structured JSON output to convert messy question blocks into canonical
Variables rows. Few-shot examples drawn from the 3 already-parsed helpers in
`AWE_Database/staging/parsed_variables.jsonl`. Prompt caching on the system
prompt + examples to keep cost down across many surveys.

### 3. API service (`api/main.py` — FastAPI)

- `POST /ingest` — `{source, survey_id?, title?, url?, file?}` → returns
  `run_id`
- `GET  /runs/{run_id}` — status + log tail
- `GET  /helper?survey_id=…&format=csv|xlsx|json` — modern Internal Helper
  Columns layout
- `GET  /helper/legacy?survey_id=…` — 6-column legacy layout
- `GET  /variables?survey_id=…&domain=…&variable_type=…` — filtered JSON
- `GET  /surveys?q=…` — typeahead by title or ID
- `GET  /openapi.json` — for the Alteryx Download tool

Auth: API keys per user. Table
`api_keys(key_hash, user_email, created_at, last_used_at, revoked_at)`. Header
`X-API-Key`. Tiny CLI to mint/revoke.

### 4. Streamlit UI (extend `/app/app.py`)

New tab **"Build helper file"**: paste survey ID or title or drop a PDF/DOCX →
`POST /ingest` → stream logs → preview the helper as a dataframe → download
XLSX/CSV. Past `ingestion_runs` for the current survey listed beside it so you
can roll back a version.

### 5. Alteryx access patterns (`docs/alteryx.md`)

1. **ODBC**: Input Data → SQLite driver → `v_helper_modern`, filter
   `survey_id`
2. **Download tool**: GET `/helper?survey_id=…&format=csv` with `X-API-Key`
3. **Run command tool**: `codebookctl pull <id> --xlsx` drops an Excel file in
   the workflow dir

### 6. Sync with the existing AWE Notion DB

SQLite is system of record. After each ingestion run, push new rows to Notion
Variables/Instruments. Nightly `scripts/sync_from_notion.py` pulls any
Rob-edited rows back (preserves `Flag = Confirmed`, manual Domain/Dimension
edits). Conflicts → `sync_conflicts.jsonl`.

## Files

```
/app/app.py                              (extend with "Build helper file" tab)
codebook_builder/
  cli.py                                 (codebookctl: ingest | pull | list | mint-key)
  sources/{qualtrics.py, document.py, link.py}
  normalize.py                           (Claude structurer, prompt-cached)
  notion_sync.py
  storage.py                             (SQLite schema + migrations)
api/{main.py, auth.py, schemas.py}
db/migrations/{0001_init.sql, 0002_views.sql}
scripts/{seed_from_notion.py, sync_from_notion.py}
docs/{alteryx.md, helper_schema.md, api.md}
tests/{test_normalize.py, test_api.py}   (golden-file tests using the 3 parseable helpers)
```

## Phasing — value early

| Phase | Outcome | Effort |
|---|---|---|
| **0. Seed** | Backfill `codebook.sqlite` from existing Notion Variables + the 3 parseable helpers; `v_helper_modern` queryable from Alteryx today | ~1 day |
| **1. Qualtrics ingest** | `codebookctl ingest --qualtrics SV_…` end-to-end → SQLite + Notion; Streamlit tab wired | ~2 days |
| **2. API + Alteryx** | FastAPI running with API keys; `docs/alteryx.md` covers all three patterns | ~1 day |
| **3. PDF / DOCX fallback** | Document parser + Claude normalizer for surveys without API access | ~2 days |
| **4. Bidirectional Notion sync + versioning UX** | Nightly reconcile, version-rollback in UI, conflict reporter | ~1 day |

## Assumptions worth flagging

1. **Qualtrics token** — existing AWE app already uses `QUALTRICS_API_TOKEN` +
   `QUALTRICS_DATACENTER`; the new pipeline reuses them.
2. **Box CFS hydration** — the AWE-DB build is currently blocked on
   un-hydrated Box files. The new pipeline uses Qualtrics first (no Box needed)
   and only falls back to Box PDFs you've marked "Make Available Offline". A
   `--require-hydrated` flag will fail loud instead of silently skipping.
3. **Single writer** — SQLite-on-Box tolerates one writer; the API server is
   it. Analysts get ODBC read-only.
4. **PII** — codebooks are metadata only (variable names, question text,
   scales) — no response data — so team-wide sharing is safe. A parse-time
   check refuses to ingest if response rows ever appear in a target file.

## Open questions to resolve before / during Phase 0

- Which workstation hosts the FastAPI process, and what's its uptime story?
  (Lab Mac? Always-on server?)
- Who on the team should get API keys at launch, and is email-based identity
  good enough for the `api_keys.user_email` column?
- Are there any RFS folders that should be excluded from ingestion for IRB
  / data-use reasons?
- Confirm the exact "Internal Helper Columns" header set — is it strictly the
  AWE Variables schema, or does the Alteryx workflow expect additional columns
  (e.g. `COURS`, `Wave`, `Cohort`)?
