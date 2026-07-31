# Update Log

Chronological record of refresh cycles. Each autonomous run appends an entry.

## 2026-06-18 — Initial build (v0.1)
- Stood up repository: schema, data dictionary, agency registry (all 51
  state-level jurisdictions with administrative structure), tidy metrics store
  with full provenance, SQLite builder + validator, autonomous-agent playbook,
  scheduled GitHub Actions refresh workflow, Notion/Sheets mirror scaffolding,
  data-source catalog, and expansion-options menu.
- Seeded **414 cited workforce observations across all 51 jurisdictions** via
  parallel web research (every value carries a source URL + confidence tier;
  nothing fabricated; missing values left absent).
- Known gaps this run: a handful of states still thin on staffing headcount,
  supervisor ratios, tenure, and time-to-fill (rarely published); BLS OEWS
  state wages recorded from search snippets (bls.gov blocks automated fetch) —
  flagged low/medium and to be re-verified against primary tables.
- Next cycles: fill remaining state gaps, re-verify BLS against primary tables,
  begin county build-out for county-administered states, and evaluate the
  Tier-1 expansion options (BLS metro wages, Census ASPEP, IPEDS pipeline).

## 2026-06-18 — v0.2: Notion mirror + Tier 1/2 expansion capability
- **Notion database created & populated** via the Notion MCP connection: all 51
  agencies with core metrics (data source `fc25ce7e-6c92-4178-9eb8-60f3b3a83287`).
- **Tier 1 + Tier 2 expansion** wired in:
  - Added 15 expansion metric keys to the data dictionary + build validator.
  - **#9 derived workload ratios** computed now (`agent/derive_metrics.py`):
    17 rows (children-per-caseworker, investigations-per-investigator) folded
    into the DB → 431 observations.
  - **#2 Census ASPEP** and **#3 IPEDS** API collectors added
    (`agent/collectors/`), wired into the weekly Action; output lands in
    `data/incoming/` for review before merge. (Census API codes need first-run
    validation; IPEDS via Urban Institute API.)
  - Remaining Tier 1/2 items (#1 metro wages, #4 IV-E partnerships, #5 salary
    schedules, #6 job-posting signal, #7 budgets, #8 ASWB licensure, #10 PIP)
    are now agent-gathered tasks in the playbook and accrue weekly.
- Cadence confirmed: weekly (Mondays 09:00 UTC).
