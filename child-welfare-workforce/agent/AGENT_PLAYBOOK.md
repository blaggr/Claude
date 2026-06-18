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
6. **Run expansion collectors + derivations** (see "Expansion pipeline" below),
   review their `data/incoming/*.csv` output, and merge trustworthy rows into
   `data/metrics.csv`. Then regenerate derived metrics.
7. **Rebuild & report.** `python db/build_db.py` rebuilds `db/cww.db`;
   `python agent/coverage_report.py` regenerates `docs/COVERAGE.md`.
8. **Mirror.** Sync the agency summary to Notion (database
   `fc25ce7e-6c92-4178-9eb8-60f3b3a83287`) via the Notion MCP tools, or run
   `python mirror/to_notion.py` / `to_sheets.py` if credentials are present.
9. **Log.** Append a dated entry to `agent/update_log.md` summarizing what
   changed (agencies touched, rows added/updated, notable findings).
10. **Open a PR.** Commit to the working branch and open/update a draft PR so a
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

## Expansion pipeline (Tier 1 + Tier 2 — see docs/EXPANSION_OPTIONS.md)

Each cycle, run the automated collectors and the derivation step. Collectors
write to `data/incoming/` and never auto-merge — review for sanity, then append
trustworthy rows to `data/metrics.csv` (quoting any commas).

Automated (deterministic, run in the weekly Action):
- `python agent/collectors/ipeds_social_work.py` — T1 #3 degree-pipeline supply
  (Urban Institute / IPEDS). Reliable; verify award-level codes once.
- `python agent/collectors/census_aspep.py` — T1 #2 public-welfare employment &
  payroll (Census ASPEP). **Validate the API path/function/var codes on first
  run** and map FIPS agency_ids to `US-<USPS>` before merging.
- `python agent/derive_metrics.py` — T2 #9 derived workload ratios. Regenerates
  `data/derived_metrics.csv` (idempotent; folded in by build_db).

Agent-gathered each cycle (research, same cite-everything rules; new metric keys
already in the data dictionary):
- T1 #4 `title_iv_e_partnership` / `title_iv_e_stipends_annual` — state IV-E
  university education partnerships (finite list; CalSWEC etc.).
- T1 #5 `caseworker_salary_step_count` + fuller salary schedules.
- T2 #6 `cw_job_postings_open` — open caseworker postings as a vacancy signal.
- T2 #7 `agency_personnel_budget_usd` / `funded_caseworker_positions` — budgets.
- T2 #8 `aswb_licensed_social_workers` — ASWB licensure counts.
- T2 #10 `cfsr_pip_workforce_measure` — CFSR PIP workforce targets/status.

T1 #1 (BLS metro wages) maps to a metro, not a state agency; add when the
county/metro dimension lands (see county build-out).
