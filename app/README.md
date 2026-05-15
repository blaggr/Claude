# AWE Survey Analyzer (Streamlit)

A local dashboard that wraps the `qualtrics-awe-analysis` Claude skill so you can enter Qualtrics survey IDs/titles in a form and trigger the full pull → analyze → render pipeline with one click.

## Setup

```bash
pip install -r app/requirements.txt
```

Set Qualtrics credentials in your shell (or use the sidebar override at runtime):

```bash
export QUALTRICS_API_TOKEN="…"
export QUALTRICS_DATACENTER="iad1"   # the prefix of your Qualtrics URL
```

## Run

From the repo root:

```bash
streamlit run app/app.py
```

Opens at `http://localhost:8501`.

## What the app does

1. Add one row per Qualtrics survey: paste a survey ID (`SV_…`) **or** a title substring. Pick its role (`post`, `pre`, `followup`).
2. Set the join key column (default `ParticipantID`) and a report title.
3. Click **Run analysis**. The app shells out to the three skill scripts (`pull_qualtrics.py` → `analyze.py` → `render_report.py`) and streams logs into the page.
4. The generated HTML dashboard appears inline and is also downloadable.
5. Past runs are listed in the sidebar — click any to re-open without re-running.

## Output

Each run writes to `awe-reports/<slug>-<YYYYMMDD-HHMMSS>/`:
- `raw/` — Qualtrics CSV exports + question definition JSON
- `processed/summary.json` — classified questions, stats, pre/post pairs
- `AWE-report.html` — the dashboard
- `metadata.json` — title, surveys, timestamp (powers the sidebar)
