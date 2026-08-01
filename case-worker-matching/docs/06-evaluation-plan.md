# 6. Evaluation Plan

Four phases: **A** — instrument validation; **B** — simulation study; **C** —
stepped-wedge field pilot; **D** — scale-up and permanent monitoring. Phases A and B can
run in parallel after month 3. Total pre-scale timeline ≈ 30–36 months with a single
partner agency.

## Phase A — Instrument validation (months 0–9)

### A.1 Item development and content validity
- SME panels (experienced supervisors, workers across stages, training staff, tribal
  partner for ICWA-relevant content) review CCI anchors and WCP BARS; content-validity
  indexing on each anchor; revise to **I-CVI ≥ .78** (six or more experts) and
  **S-CVI/Ave ≥ .90**, with the S-CVI computation method reported (Polit & Beck, 2006;
  Polit, Beck, & Owen, 2007).
- Cognitive interviews with ~12 workers/supervisors rating think-aloud on real
  (de-identified) cases to catch anchor ambiguity before field testing.

### A.2 CCI field test
- ~300 cases sampled across stages and offices, **dual-rated independently** (worker +
  supervisor).
- Reliability targets: weighted κ ≥ .60 per domain (Landis & Koch, 1977 — "substantial,"
  acknowledging their own caveat that such benchmarks are conventions); ICC(2,1) ≥ .75
  on total score (Cicchetti, 1994; Koo & Li, 2016 note .75 is the floor of "good," so
  this is a minimum, not an aspiration); domains missing targets get anchor revision
  and a second round.
- Internal structure: CFA of the 7-domain model vs. bifactor (general complexity +
  domain specifics); the scalar weight formula assumes a meaningful general factor.
- Convergent/discriminant validity: correlations with SDM risk level and CANS totals —
  expected moderate (complexity ≠ risk); near-collinearity with SDM risk would indicate
  the CCI is re-measuring risk rather than work.

### A.3 Ongoing reliability stream
The dual-rating-at-assignment procedure (Doc 02 §2.3) makes IRR a *live* statistic, not
a one-time study; disagreement logs feed semi-annual reliability reporting forever.
In addition, a **standing blind double-rating audit** (quarterly ~5% random sample of
active cases, independently re-rated outside the unit — Doc 02 §2.7) runs permanently
from go-live: operational acuity-type systems demonstrably lose reliability without
parallel-rating audits (Fasoli & Haddock, 2010; Junttila et al., 2023), and scores that
carry workload consequences drift upward (Campbell, 1979; Silverman & Skinner, 2004;
Bosk, 2018).

### A.4 Case-weight calibration (time study)
- Random-moment sampling (preferred; diaries as fallback; methodology: Barnes, 1980;
  live child welfare precedents: Wisconsin DCF, 2021; Washington DCYF, 2023) over
  ≥ 3 months, ≥ 60 workers stratified by stage; estimate hours-per-case as a function
  of CCI domain scores, with structured expert (Delphi) review of the resulting weights
  per weighted-caseload practice (Flango & Ostrom, 1996; Pace et al., 2023).
- Model: mixed-effects regression, hours ~ domains + stage + worker random effect;
  the fixed-effect coefficients become `β_d` and stage terms become `m_stage`/`b_stage`
  (Doc 02 §2.5). Test pre-registered interactions (D1×D6, D2×D5); adopt only on material
  fit improvement.
- Criterion validity target: calibrated `w(c)` explains substantially more variance in
  logged hours than raw case count (the operative comparison; publishable either way).

### A.5 WCP validation
- BARS inter-rater reliability: subset of workers rated by two supervisors/leads
  (ICC ≥ .70 target).
- Multitrait–multimethod matrix across supervisor BARS, training records, and
  case-history counts — convergence within domain, discrimination across domains.
- Self–supervisor gap analysis (descriptive; feeds the calibration-conference design).

## Phase B — Simulation study (months 4–9, overlapping A)

Build the reference implementation (Doc 04 §4.10) and evaluate the algorithm **before
any live use**, using two data regimes:

1. **Synthetic agency**: generative model of arrivals, complexity profiles, and a
   workforce with realistic skill/tenure distributions; supports stress tests
   (vacancy waves, complexity surges, small-unit edge cases).
2. **Retrospective replay**: 12–24 months of the partner agency's actual intakes and
   staffing, replayed under (a) historical assignment as it happened, (b) rotation
   baseline, (c) CASE-MATCH online mode, (d) CASE-MATCH online + quarterly rebalancing.

Outcomes compared: mean/min match quality `M`; skill-floor violation counts; utilization
dispersion (Gini and max); severe-share distribution (constraint 7 binding rates);
share of workers > 100%; escalation counts; transfer counts under (d);
stretch-assignment volume. Sensitivity analyses over β, δ, ε, headroom, `k`, the
transfer-penalty parameters (τ₀, φ), and the severe-share cap ρ_max — the transfer
penalty and severe-share analyses are **mandatory**, because those parameters are
policy choices, not empirical estimates (Doc 07 §7.2, §7.8) — reported as tornado plots
so the steering body sees which knobs matter. Pre-registered decision rule: proceed to
pilot only if simulated CASE-MATCH dominates rotation on floors *and* dispersion
without degrading mean match quality.

## Phase C — Stepped-wedge cluster pilot (months 10–30)

### Design
- **Unit of randomization:** supervisory unit (natural cluster; contamination across
  units is limited because assignment happens within unit). ~16–24 units, 4–6 steps,
  one cluster-group crossing to CASE-MATCH per step after a baseline period; all units
  exposed by the final step. Stepped wedge fits the reality that the agency intends to
  adopt (no unit can stay control forever) and handles secular trends (hiring waves,
  policy changes) better than a parallel design of feasible size.
- **Intervention package:** decision-support assignment + monthly rebalancing
  recommendations + supervisor training; control condition is practice-as-usual
  (typically rotation + intuition).

### Outcomes (pre-registered hierarchy)
- **Primary:** (1) workload equity — within-unit utilization dispersion; (2) worker
  well-being — burnout (MBI: Maslach & Jackson, 1981; Maslach et al., 2016; or ProQOL:
  Stamm, 2010) measured quarterly.
- **Secondary (worker/process):** turnover intention and actual separations —
  registered as a **distinct outcome family from well-being**, since well-being gains
  do not automatically convert to retention (the QIC-WD Resilience Alliance trial
  improved coping without reducing turnover — Prince et al., 2023 — while selection and
  organizational-climate interventions did move retention; QIC-WD, 2023); timeliness of
  statutory contacts and court reports; skill-floor violation rate; severe-share cap
  binding rates; override rate, reasons, and override-vs-recommendation outcome quality
  (Doc 04 §4.7); time-to-assignment.
- **Exploratory (child/family, honest about power):** re-referral within 6/12 months,
  placement stability, time-to-permanency, worker-change counts per case. The pilot will
  likely be under-powered for these distal outcomes; they are estimated and reported
  with that framing, powering the *next* study.

### Analysis and power
- Mixed-effects models with fixed step (period) effects, random unit effects, and the
  standard stepped-wedge exposure term (design: Hussey & Hughes, 2007; Hemming et al.,
  2015 — who explicitly endorse stepped wedge when the intervention will roll out to
  all clusters; social work precedent: Chen, Pan & Kainz, 2021); robustness checks
  with cluster-period bootstrap; explicit modeling of secular workforce trends (hiring
  waves, caseload-composition shifts) via the period effects and workforce covariates.
- **Power analysis uses closed-cohort methods, not the cross-sectional model.** The
  same ~7 workers per unit are measured repeatedly across periods, so the
  Hussey–Hughes exchangeable model overstates power; calculations follow Hooper et al.
  (2016) and Hemming & Taljaard (2016), incorporating within-worker autocorrelation and
  a decaying cluster autocorrelation (CAC). With 20 units, 5 steps, ~7 workers/unit,
  and ICC .05–.15, the minimum detectable standardized effect is reported as a
  **sensitivity range over ICC and CAC — realistically d ≈ 0.30–0.40** — rather than a
  point value. Formal calculation with agency-specific ICC/CAC estimates (e.g., via the
  Hemming group's Shiny CRT Calculator) is a pre-registration deliverable.

### Implementation strand
- Framed in CFIR (determinants) with RE-AIM reporting (reach, adoption, implementation
  fidelity, maintenance).
- Fidelity indicators: % assignments made through the system; recommendation-viewed
  rate; override rate with reasons; rebalancing recommendations reviewed.
- Qualitative: supervisor and worker interviews at 3 and 12 months post-crossover on
  trust, gaming, and workflow fit; family-partner advisory review of the family-facing
  statement (Doc 05 §5.5).

### Safety monitoring
A standing review (steering body, Doc 05 §5.6) with the pre-stated kill criteria; plus
pilot-specific stopping rules: any evidence the tool delays urgent assignments beyond
SLA, or sustained escalation-queue breach.

## Phase D — Scale-up and permanent monitoring (months 30+)

- Staged rollout by office, each office starting in shadow mode (recommendations logged,
  not shown) for one month to verify local calibration before going live.
- **Recalibration schedule:** case weights re-checked against a light-touch time study
  every 2 years or after major policy change; BARS anchors reviewed annually; component
  weights only via steering-body change control (logged, Doc 05 §5.5).
- **Drift monitoring:** score distributions by office/rater; override rates; equity
  audits (Doc 05 §5.3) on their semi-annual cycle.
- **Research outputs:** the framework supports at least four publishable studies —
  (1) CCI/WCP psychometrics (Phase A), (2) simulation comparison (Phase B), (3) the
  stepped-wedge trial (Phase C), and (4) the capability-gap pricing analysis
  (Doc 04 §4.9) linking optimization duals to training investment — plus a methods paper
  on the governance model.

## Threats to validity (selected, with responses)

| Threat | Response |
|---|---|
| Reactivity of rating (scores drift once they carry workload consequences) | Dual rating; live IRR stream; periodic time-study re-checks against `w(c)` |
| Contamination (supervisors in control units imitate the tool) | Unit-level randomization; fidelity measurement in both arms; stepped wedge tolerates partial contamination better than parallel designs |
| Secular workforce shocks (hiring waves, vacancies) | Step fixed effects; workforce covariates; simulation stress tests define expected behavior under shock |
| Hawthorne / novelty on burnout self-report | Behavioral co-primaries (dispersion is computed, not reported); turnover as secondary |
| Small-unit instability (units of 5–8) | Office-level pooling for cross-unit routing; sensitivity analyses excluding smallest units |
