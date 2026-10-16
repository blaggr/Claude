# CLAUDE.md — Child Welfare Workforce Database

Guidance for any Claude Code session working in this project (interactive or the
scheduled refresh). Read `agent/AGENT_PLAYBOOK.md` for the full cycle.

## What this project is
An autonomously-maintained, fully-cited database of child welfare **workforce**
metrics for every U.S. public child welfare agency (state-level now; county
where public data exists). Source of truth = `data/*.csv` → built into
`db/cww.db` by `db/build_db.py`.

## Non-negotiable rules
1. **Never fabricate a value.** Every metric row needs a real, resolvable
   `source_url`. Missing data is left absent — never estimated to fill a cell.
2. **Cite + tier everything** (source, URL, year, confidence high/medium/low).
3. **Validate before commit:** `python db/build_db.py --check` must pass.
4. **Preserve history** — add a new `period_year` row, don't overwrite.
5. **Controlled vocabulary** — `metric_key` values must be in
   `schema/data_dictionary.md` (and `KNOWN_METRIC_KEYS` in `db/build_db.py`).
   To add a measure, update both, then add rows.

## Common tasks
- Build/validate: `python db/build_db.py`
- See gaps / pick work: `python agent/pick_targets.py 8`
- Refresh coverage doc: `python agent/coverage_report.py`
- Mirror (optional, needs creds): `python mirror/to_sheets.py`, `mirror/to_notion.py`

## CSV gotchas
- Always quote any field containing a comma — **including URLs** (several
  federal/state PDF URLs contain literal commas) and `notes`.
- Put numbers in `value_numeric` (no `%`, `$`, or thousands commas), text in
  `value_text`; annualize hourly wages and note it.

## Editing conventions
- Keep `agencies.csv` admin-structure changes citation-backed.
- Match the existing row style; keep `notes` short and caveat-focused.
- After data changes: rebuild DB, regenerate `docs/COVERAGE.md`, append
  `agent/update_log.md`, then open a **draft** PR.

## Environment note
Direct `curl`/HTTP and `bls.gov`/`acf.gov` automated fetch are often blocked
here. Gather via WebSearch + WebFetch; read figures from search snippets when
primary PDFs won't fetch, and lower confidence accordingly.
