# Expansion Options — Other Public Data We Could Add

A prioritized menu of additional **public** data we can fold into the database
to make it more useful to a workforce expert. Each entry: what it adds, source,
granularity, build effort, and why it matters. Effort is the work to integrate
reliably (easy = structured/known URL; medium = per-state PDFs/snippets; hard =
licensing, scraping, or heavy normalization).

Tell me which of these to prioritize and I'll wire them into the next refresh
cycles. My recommended first three are marked ⭐.

**Status (v0.2):** Tier 1 + Tier 2 selected for build-out. Metric keys for all
of them are now in the data dictionary. **Built this cycle:** #9 derived
workload ratios (live in the DB); #2 Census ASPEP and #3 IPEDS pipeline
collectors (run weekly in CI → `data/incoming/` for review). The remaining
Tier 1/2 items (#1, #4, #5, #6, #7, #8, #10) are gathered by the weekly agent
per `agent/AGENT_PLAYBOOK.md` and accumulate over cycles.

## Tier 1 — high value, tractable

⭐ **1. BLS OEWS metro-level wages (SOC 21-1021)** — adds sub-state wage
competitiveness (a caseworker in metro A vs. rural B). Source: BLS OEWS
metropolitan tables. Granularity: metro. Effort: easy–medium. Why: pay
competitiveness is a top driver of turnover; statewide means hide it.

⭐ **2. Census ASPEP — public welfare employment & payroll** — independent,
consistent, all-states/all-years series for government social-services
employment and payroll. Source: Census API. Granularity: state + local govt.
Effort: easy (real API). Why: a neutral cross-check on agency-reported staffing
and a long time series for trends.

⭐ **3. IPEDS social work degree completions (pipeline supply)** — BSW/MSW
graduates per state per year = the hiring pipeline. Source: NCES IPEDS
(completions by CIP 44.07). Granularity: institution → state. Effort: easy
(downloadable). Why: lets you compare workforce demand to local degree supply —
a core workforce-planning question.

**4. Title IV-E university partnership / stipend programs** — counts of
stipended students committed to public child welfare (e.g., CalSWEC in CA, and
~40 other state IV-E education partnerships). Source: program sites/reports.
Granularity: state. Effort: medium. Why: direct measure of the subsidized
pipeline into agencies.

**5. State salary schedules / classification pay bands (structured)** — replace
job-posting snippots with full step-and-grade tables for the caseworker series.
Source: state HR/personnel sites. Granularity: state (county for county-admin).
Effort: medium. Why: precise entry/mid/max pay and step progression, not just a
single posting.

## Tier 2 — valuable, more effort

**6. Public-sector job-posting volume as a leading vacancy indicator** — count
of open caseworker postings over time (e.g., governmentjobs.com / NEOGOV public
listings, state career portals). Granularity: state/county. Effort: medium–hard
(scraping, dedup). Why: a near-real-time proxy for vacancy pressure between
annual reports.

**7. State budget appropriations for child welfare agencies** — funded
positions, personnel budgets, vacancy-savings factors. Source: state budget
books / legislative fiscal offices (USAspending for federal IV-B/IV-E flows).
Granularity: state. Effort: medium. Why: funded-vs-filled is the cleanest
vacancy measure and ties workforce to dollars.

**8. ASWB social work licensure data** — licensed social workers per state,
exam pass rates, demographics. Source: ASWB reports. Granularity: state.
Effort: medium (some reports paywalled/aggregate). Why: licensure supply &
diversity context for states that require/encourage SW licensure.

**9. Derived workload ratios** — combine AFCARS/NCANDS caseload with our staff
counts to compute children-per-worker and investigations-per-investigator
consistently across states. Source: internal join. Effort: easy once #2 and our
staffing improve. Why: comparable workload metric where states don't publish one.

**10. CFSR Program Improvement Plan (PIP) workforce measures** — workforce-
specific improvement targets and status. Source: ACF/state PIPs. Granularity:
state. Effort: medium. Why: shows which states are formally working workforce
problems and against what targets.

## Tier 3 — niche / heavier lift

**11. Demographic composition of the workforce** (race/ethnicity/gender, and
worker–child demographic match). Source: some APSRs, audits (e.g., AK). Effort:
hard (sparse, inconsistent). Why: equity analysis; worker–child match research.

**12. Collective bargaining agreements** — union salary steps, caseload
language, premium pay. Source: state/county + union sites. Effort: hard. Why:
authoritative on pay progression and contractual caseload caps.

**13. Cost-of-living / wage-competitiveness index** — normalize salaries by
local COLA or a comparable-occupation benchmark. Source: BEA RPP, MIT Living
Wage. Effort: medium. Why: real (not nominal) pay competitiveness.

**14. Foster-care entry/exit & maltreatment trends as demand drivers** — fuller
AFCARS/NCANDS time series joined to workforce. Effort: medium. Why: explains
caseload pressure changes over time.

**15. County-level workforce build-out** — deepen county rows for
county-administered states (CA, CO, MD, MN, NY, NC, OH, PA, VA, WI) using
CCWIP, county budgets, PCSAO Factbook, NYC ACS, LA DCFS, Cook County, etc.
Effort: hard (per-county). Why: the original goal's full granularity.

---
### How to choose
If the near-term use is **workforce planning**, prioritize 1, 2, 3, 5, 7.
If it's **turnover/retention research**, prioritize 6, 8, 9, 10, 11.
If it's **the full county-level vision**, prioritize 15 (and 5 for county-admin pay).
