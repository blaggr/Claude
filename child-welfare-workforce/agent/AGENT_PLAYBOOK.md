# Child Welfare Workforce Agent — Operating Playbook

This file is the operating manual for the autonomous agent that builds and
maintains the Child Welfare Workforce Database (CWW-DB). A scheduled job
(`.github/workflows/cww-refresh.yml`) launches a Claude Code session that reads
this playbook and executes one **refresh cycle**.

## Mission
Maintain an accurate, fully-cited national database of child welfare
**workforce** metrics for every public child welfare agency at the state level
(51 jurisdictions) and, where public data exists, the county level.

## Prime directives (non-negotiable)
1. **Never fabricate.** A value enters the database only with a real,
   resolvable `source_url`. Missing data is left absent, never guessed.
2. **Cite everything.** Every metric row carries source name, URL, pub date,
   the year it describes, and a confidence tier (high/medium/low).
3. **Prefer official > secondary > estimate.** State APSR/CFSP, legislative
   audits, and federal datasets outrank news; news citing official figures
   outranks aggregators; aggregators are `low` confidence.
4. **Preserve history.** Do not delete superseded values — add the newer
   `period_year` row so trends remain queryable.
5. **Be honest about scope.** A reported "caseworker" count is often a broader
   staff count; capture the caveat in `notes`.

## One refresh cycle
A cycle works through a slice of jurisdictions (don't try all 51 every run —
rotate, prioritizing staleness). Steps:

1. **Pick targets.** Run `python agent/pick_targets.py` to get the N agencies
   with the stalest or thinnest data (oldest `collected_at`, fewest metrics).
2. **Gather.** For each target, fan out web research (WebSearch + WebFetch)
   over the source hierarchy in `docs/DATA_SOURCES.md`. Search patterns that
   work well:
   - `"<state> APSR <year> child welfare workforce turnover vacancy"`
   - `"<state> DCF/DCS/DSS caseworker turnover rate <year>"`
   - `"<state> child welfare caseload standard caseworker salary"`
   - `site:bls.gov OEWS 21-1021 <state>` (read from snippets; bls.gov blocks fetch)
3. **Extract → rows.** Emit rows in the exact `data/metrics.csv` schema
   (see `schema/data_dictionary.md`). Controlled `metric_key` vocabulary only.
4. **Reconcile.** For each (agency, metric, year), keep the highest-confidence
   value. If a new figure contradicts an existing same-year one, keep both only
   if sources genuinely differ; otherwise prefer the official source and note it.
5. **Validate.** `python db/build_db.py --check` must pass (schema, units,
   provenance). Fix issues before committing.
6. **Rebuild & report.** `python db/build_db.py` rebuilds `db/cww.db`;
   `python agent/coverage_report.py` regenerates `docs/COVERAGE.md`.
7. **Mirror (optional).** If mirror credentials are present, run
   `python mirror/to_notion.py` / `to_sheets.py`.
8. **Log.** Append a dated entry to `agent/update_log.md` summarizing what
   changed (agencies touched, rows added/updated, notable findings).
9. **Open a PR.** Commit to the working branch and open/update a draft PR so a
   human can review the diff. The diff IS the record of changes.

## County expansion (tiered)
State-level coverage comes first. Layer counties in for
county-administered/state-supervised states (CA, CO, MD, MN, NY, NC, OH, PA,
VA, WI, and hybrids ND/NV) where a public county source exists. Add county rows
to `agencies.csv` (`jurisdiction_level=county`) before adding their metrics.
Good county leads: California CCWIP (UC Berkeley), county CFSRs/QSRs, county
budget books, large-county dashboards (LA DCFS, NYC ACS, Cook County, etc.).

## Data-quality guardrails
- Flag as `low` confidence: figures >3 years old, salary-aggregator data,
  numbers where "caseworker" vs "all staff" is ambiguous, derived percentages.
- When a state privatizes case management (e.g., KS, NE, FL CBCs), note that
  workforce figures may describe contractors, not public employees.
- Distinguish point-in-time (vacancy on a date) from period figures (annual
  turnover).

## What NOT to do
- Don't scrape behind logins or paywalls.
- Don't store PII — only aggregate workforce statistics.
- Don't overwrite the human-curated `agencies.csv` admin-structure column
  without a citation for the change.
