# Data Sources — Child Welfare Workforce Database

The authoritative/primary sources the agent draws on. For each: owner,
granularity, cadence, access, and which of our four metric families it feeds
(STAFF = staffing/vacancy, TURN = turnover/tenure, LOAD = caseload/workload,
PAY = pay/demographics/qualifications). "Context" = demand drivers that frame
workforce strain rather than measure the workforce directly.

> Reality of access: there is **no single national feed** of county/state
> child-welfare *workforce* headcounts. Federal sources are strong for **demand
> context** and consistent **wage benchmarks**; the actual workforce numbers
> (vacancy, turnover, caseload) come state-by-state from APSRs, legislative
> audits, court-monitoring reports, and agency dashboards. The agent must
> triangulate. Many federal sites (bls.gov, acf.gov) block automated fetch, so
> the agent reads figures from search snippets and the published PDFs.

## Federal / national

| Source | Owner | Granularity | Cadence | Access | Feeds |
|--------|-------|-------------|---------|--------|-------|
| **Child & Family Services Plan (CFSP) / Annual Progress & Services Report (APSR)** | ACF Children's Bureau (each state submits) | State | Annual | PDF on state sites | STAFF, TURN, LOAD — the single richest workforce narrative per state |
| **CFSR Round 4 (Statewide Assessment + Final Report)** | ACF Children's Bureau | State | ~7-yr cycle | PDF (acf.gov) | TURN, LOAD, STAFF (workforce is a systemic factor) |
| **AFCARS** (Adoption & Foster Care Analysis & Reporting System) | ACF Children's Bureau | State (county in some state extracts) | Semi-annual / annual dashboard | Dashboard + data files | Context: children in foster care, entries/exits |
| **NCANDS / Child Maltreatment report** | ACF Children's Bureau | State | Annual | PDF + data files | Context: referrals, investigations, victims |
| **BLS OEWS — SOC 21-1021 Child, Family & School Social Workers** | Bureau of Labor Statistics | National, state, metro | Annual (May) | HTML/XLSX (blocks bots → use snippets) | PAY benchmark (employment + mean/median wage) |
| **BLS OEWS — SOC 21-1099 Social Workers, All Other** | BLS | National/state | Annual | HTML/XLSX | PAY benchmark (supplementary) |
| **Census Annual Survey of Public Employment & Payroll (ASPEP)** | U.S. Census Bureau | State, local govt | Annual | API + tables | STAFF/PAY context: public-welfare-function employment & payroll |
| **QIC-WD (Quality Improvement Center for Workforce Development)** | UNL / Children's Bureau grant | Site-specific + synthesis | Ad hoc | Web + reports | TURN — turnover measurement methodology & site data |
| **NSCAW III Workforce Study** | ACF OPRE | National sample | Periodic | Reports | TURN — reasons for caseworker turnover |
| **National Child Welfare Workforce Institute (NCWWI)** | Children's Bureau grant | National | Ongoing | Web/reports | STAFF/TURN — frameworks, university partnerships |
| **KIDS COUNT Data Center** | Annie E. Casey Foundation | State + county | Annual | Web + API | Context: foster care, child population denominators |
| **Casey Family Programs** | Casey Family Programs | State case studies | Ad hoc | Web/reports | TURN/LOAD — state retention case studies |
| **CWLA & COA caseload/workload standards** | Child Welfare League of America; Council on Accreditation | National standard | Static | Web | LOAD benchmark (recommended caseload ratios) |

## State / local (examples the agent uses)

| Source | Granularity | Feeds | Notes |
|--------|-------------|-------|-------|
| **State APSR/CFSP PDFs** | State (sometimes region) | STAFF, TURN, LOAD | Primary per-state workforce source |
| **State legislative auditor / performance audits** | State | STAFF, TURN, LOAD | e.g. TN Comptroller, AK Legislative Audit, LA LLA, ME OPEGA |
| **Court-monitoring reports (consent decrees)** | State / large county | LOAD, STAFF | e.g. SC *Michelle H.*, MI *Dwayne B.*, WI *Jeanine B.*, RI *Andrew C.* |
| **State HR class specs / job postings** | State | PAY | Salary ranges, education/licensure requirements |
| **California CCWIP (UC Berkeley)** | County | LOAD, Context | County-level CA child welfare indicators |
| **Texas DFPS Data Book & Rider reports** | State/region | STAFF, TURN, LOAD | Strong structured agency data |
| **PCSAO Factbook (Ohio)** | County | LOAD, Context | County-by-county profiles |
| **State KIDS COUNT affiliates** | State/county | Context | Foster care & maltreatment series |

## Data-quality conventions
- Confidence tiers (high/medium/low) per `schema/data_dictionary.md`.
- "Caseworker" definitions vary (investigators vs. ongoing vs. all staff) — the
  agent records the caveat in `notes`.
- Privatized case management (e.g., KS, NE Eastern, FL CBC lead agencies) is
  flagged because figures may describe contractors, not public employees.
