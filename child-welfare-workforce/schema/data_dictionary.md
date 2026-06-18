# Data Dictionary — Child Welfare Workforce Database (CWW-DB)

Every metric is stored as a row in `metrics` with a controlled `metric_key`.
This is the canonical list. **Adding a new measure = adding a new key here +
rows in the CSV. No schema migration required.** Keep keys stable; if a
definition changes materially, create a new key rather than redefining.

## Identifier conventions

| Field | Convention | Example |
|-------|-----------|---------|
| `agency_id` (state) | `US-<USPS>` | `US-CA` |
| `agency_id` (county) | `US-<USPS>-<County_Name>` (spaces → `_`) | `US-CA-Los_Angeles` |
| `state` | USPS 2-letter | `CA`, `DC` |

## Metric keys

### Staffing & vacancy
| key | unit | meaning |
|-----|------|---------|
| `caseworker_headcount` | count | Filled frontline caseworker positions (persons) |
| `caseworker_fte` | count | Frontline caseworker full-time equivalents |
| `budgeted_caseworker_positions` | count | Authorized/budgeted caseworker positions |
| `vacancy_count` | count | Unfilled budgeted caseworker positions |
| `vacancy_rate_pct` | pct | Vacant ÷ budgeted caseworker positions |
| `supervisor_count` | count | Frontline supervisors |
| `supervisor_to_caseworker_ratio` | ratio | Caseworkers per supervisor (e.g. 5 = 1:5) |

### Turnover & tenure
| key | unit | meaning |
|-----|------|---------|
| `caseworker_turnover_rate_pct` | pct | Annual caseworker separation/turnover rate |
| `supervisor_turnover_rate_pct` | pct | Annual supervisor turnover rate |
| `avg_tenure_years` | years | Average caseworker tenure |
| `time_to_fill_days` | days | Average days to fill a vacant position |
| `preventable_turnover_rate_pct` | pct | Turnover deemed avoidable (where reported) |

### Caseload & workload
| key | unit | meaning |
|-----|------|---------|
| `avg_caseload_per_caseworker` | count | Average open cases (or children) per worker |
| `recommended_caseload_standard` | count | CWLA/COA/state standard for comparison |
| `pct_caseworkers_over_standard` | pct | Share of workers exceeding the standard |
| `children_in_foster_care` | count | Point-in-time children in out-of-home care (demand context) |
| `children_served_total` | count | Children served in period (demand context) |
| `cps_referrals_annual` | count | Maltreatment referrals received per year |
| `cps_investigations_annual` | count | Investigations/assessments per year |

### Pay, qualifications & demographics
| key | unit | meaning |
|-----|------|---------|
| `caseworker_entry_salary_usd` | usd | Starting annual salary |
| `caseworker_median_salary_usd` | usd | Median annual salary |
| `caseworker_salary_max_usd` | usd | Top of published salary range |
| `min_education_required` | (text) | e.g. "Bachelor's degree", "BSW/MSW" |
| `licensure_required` | (text) | e.g. "Yes — LSW", "No" |
| `pct_staff_with_social_work_degree` | pct | Share holding a social work degree |
| `annual_preservice_training_hours` | hours | Required pre-service training hours |
| `pct_staff_female` / `pct_staff_bipoc` | pct | Demographic composition (where reported) |

### Federal benchmark (BLS OEWS, SOC 21-1021)
| key | unit | meaning |
|-----|------|---------|
| `bls_social_workers_employment` | count | State employment, Child/Family/School Social Workers |
| `bls_social_workers_mean_wage_usd` | usd | State mean annual wage |
| `bls_social_workers_median_wage_usd` | usd | State median annual wage |

> BLS OEWS covers a broader occupation than agency caseworkers; it is a
> consistent national **benchmark**, not an agency headcount. Always compare,
> never substitute.

### Descriptors (also mirrored into the `agencies` dimension)
| key | unit | meaning |
|-----|------|---------|
| `admin_structure` | (text) | state-administered / county-administered / state-supervised-county-administered / hybrid |
| `county_data_availability` | (text) | Free-text note on whether/where county-level workforce data exists |

## Confidence tiers
- **high** — official agency report, legislative audit, or federal dataset.
- **medium** — reputable secondary source citing official data (Casey, QIC-WD, KIDS COUNT, credible news quoting the agency).
- **low** — estimate, older-than-3-years figure, or ambiguous definition.

## Rules for entering data
1. No value without a real, resolvable `source_url`.
2. Never fabricate or interpolate. Missing = absent row.
3. Prefer the most recent `period_year`; keep older rows for trend history.
4. Wrap any CSV field containing a comma in double quotes.
