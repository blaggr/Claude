---
name: qualtrics-awe-analysis
description: Pull Qualtrics survey data for an Academy for Workforce Excellence (AWE) e-learning, classify questions into Kirkpatrick dimensions (quality process / immediate outcomes / transfer / long-term outcomes), and render a self-contained HTML dashboard report. Use when the user asks to analyze AWE training surveys, build an AWE post-training report, or summarize AWE pre/post/follow-up survey results.
---

# Qualtrics AWE Analysis

Builds an evaluation report for an Academy for Workforce Excellence (AWE) e-learning from one or more Qualtrics surveys. The pipeline pulls responses via the Qualtrics REST API, classifies each question against a four-level Kirkpatrick framework, computes pre/post deltas when applicable, and renders a self-contained HTML dashboard.

## When to use

Invoke this skill when the user:
- Names one or more Qualtrics surveys (by ID or title) and asks for an AWE analysis
- Asks for an "AWE report", "AWE dashboard", or "training evaluation" against a Qualtrics source
- Wants Kirkpatrick-framed summaries of training survey data

## Inputs

The user provides one or more of:
- Qualtrics **survey IDs** (start with `SV_`)
- Qualtrics survey **titles** (the skill resolves them via the list-surveys endpoint and matches case-insensitively, substring allowed)
- An optional **role** for each survey: `pre`, `post`, or `followup` (default: `post`)
- An optional **join key** column name (default: `ParticipantID`; alternatives: `EmployeeID`, `Q_EmployeeID`, etc.)

Survey shapes the skill supports (per the AWE program):
- Post only
- Pre + post
- Post + follow-up
- Pre + post + follow-up

## Required environment

The skill expects these environment variables to be set before invocation:
- `QUALTRICS_API_TOKEN` — REST API v3 token
- `QUALTRICS_DATACENTER` — e.g. `iad1`, `fra1`, `syd1` (the prefix of your Qualtrics URL)

If either is missing, stop and tell the user how to set them. Do not prompt for the token inline; instruct them to export it.

## Workflow

Follow these steps every run. Don't skip steps — and don't add ones the user didn't ask for.

### 1. Gather inputs

Ask the user for:
- The survey IDs or titles to include (one or many)
- The role of each (`pre` / `post` / `followup`) — only if there's more than one
- The join key field name (skip if a single survey)
- An output directory (default: `./awe-reports/<slug>-<YYYYMMDD>/`)

If the user already specified everything in their request, don't re-ask.

### 2. Verify environment

Check `QUALTRICS_API_TOKEN` and `QUALTRICS_DATACENTER` are set. If not, stop with a clear instruction.

### 3. Pull responses

Run `scripts/pull_qualtrics.py` once per survey:

```bash
python3 scripts/pull_qualtrics.py \
  --survey "<id-or-title>" \
  --role <pre|post|followup> \
  --out <output-dir>/raw/
```

The script:
- Resolves titles to IDs via `GET /API/v3/surveys`
- Fetches the survey definition via `GET /API/v3/survey-definitions/{id}` (needed for question text and choice labels)
- Starts a CSV response export via `POST /API/v3/surveys/{id}/export-responses`
- Polls progress, downloads the zip, and unpacks the CSV
- Saves: `<role>_<surveyID>.csv` (responses) and `<role>_<surveyID>.definition.json` (questions/choices)

### 4. Classify and prepare

Run `scripts/analyze.py`:

```bash
python3 scripts/analyze.py \
  --raw <output-dir>/raw/ \
  --join-key ParticipantID \
  --out <output-dir>/processed/
```

The script:
- Loads each `<role>_<id>.csv` plus its definition
- Maps each question to a Kirkpatrick level using keyword heuristics from `reference/kirkpatrick_keywords.json`:
  - **L1 Reaction → Quality Process** (satisfaction, instructor, content, materials, pace, recommend)
  - **L2 Learning → Immediate Outcomes** (knowledge, understand, confidence, able to, skill)
  - **L3 Behavior → Transfer of Learning** (apply, on the job, in my role, since the training, implement)
  - **L4 Results → Long-term Outcomes** (impact, performance, productivity, results, team/business outcomes)
- For pre+post pairs, finds matched-stem questions (e.g. "I am confident I can…" appearing in both) and computes paired deltas by participant when the join key is present
- Computes per-question stats: n, mean (for numeric Likert), distribution, top free-text themes (simple keyword frequency)
- Writes `summary.json` and per-dimension tables to the processed directory

### 5. Render the dashboard

Run `scripts/render_report.py`:

```bash
python3 scripts/render_report.py \
  --processed <output-dir>/processed/ \
  --out <output-dir>/AWE-report.html
```

The script renders a single self-contained HTML file with embedded Chart.js (loaded via CDN; falls back to inline SVGs when `--offline` is passed). The dashboard has four sections matching the Kirkpatrick levels and an executive summary on top.

### 6. Show the user the report

After rendering, send the HTML file to the user with `SendUserFile` and a one-line summary of headline numbers (response counts, top L2 confidence gain, biggest transfer barrier if surfaced).

## Defaults and conventions

- Default output directory: `./awe-reports/<survey-slug>-<YYYYMMDD>/`
- Join key default: `ParticipantID` (the script also tries `EmployeeID`, `Employee_ID`, `Q_EmployeeID` if the primary isn't found)
- Likert detection: any question whose choice labels include "Strongly agree" / "Strongly disagree" / a 1–5 or 1–7 numeric scale
- Pre/post matching: case-insensitive normalized question stem (first 80 chars after stripping "Before the training," / "After the training," / "Now that you have completed…" prefixes)
- Color palette in the report uses an AWE-neutral set: `#0F3D5C` (primary), `#2E8B8B` (secondary), `#E8A33D` (accent), `#A33D3D` (delta down), `#3DA365` (delta up)

## Reference files

- `scripts/pull_qualtrics.py` — Qualtrics REST client (no extra deps beyond `requests`)
- `scripts/analyze.py` — Classification, joining, stats
- `scripts/render_report.py` — HTML dashboard generator
- `templates/dashboard.html.j2` — Single-file template (Jinja2; falls back to `string.Template` if Jinja isn't installed)
- `reference/kirkpatrick_keywords.json` — Editable keyword lists per dimension; tweak this rather than the code when adapting to a new training topic

## Edge cases to handle

- **Title resolves to multiple surveys**: stop and ask the user to pick by ID
- **Export hits rate limits**: the puller backs off with 2s/4s/8s/16s waits
- **No join key column found**: warn, skip pre/post pairing, still produce per-survey breakdowns
- **Free-text-only questions**: include top 10 keyword counts; flag for manual review in the report rather than over-claiming themes
- **Single-survey, post-only**: omit pre/post comparison panels; still classify into the four dimensions
- **Long-term outcomes survey missing**: render the L4 panel with a "no follow-up survey provided" placeholder rather than skipping the section
