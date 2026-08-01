# 1. Background, Evidence Base, and Design Rationale

## 1.1 The problem: assignment is the last unsystematized decision

Public child welfare agencies have spent three decades building structured tools for
almost every family-facing decision — screening (structured decision-making hotline
tools), safety and risk assessment (SDM), needs assessment (CANS), placement matching,
and reunification review. The decision of **which caseworker carries which case** has
received almost none of that attention. In most agencies it is governed by:

- **Rotation** ("next worker up"), which is procedurally fair to workers but blind to
  fit and to weighted workload;
- **Geography or program silo**, which constrains but does not select;
- **Raw caseload counts**, which treat a medically fragile infant with a contested ICWA
  jurisdiction question and a stable kinship placement as equal units of work;
- **Supervisor intuition**, which is often good but undocumented, uneven across units,
  and vulnerable to exactly the pressures (vacancies, crises) under which it matters most.

The consequences are well documented even if the assignment mechanism itself is rarely
studied directly (full evidence review in [07-literature-synthesis.md](07-literature-synthesis.md)):

- **Workload predicts worker outcomes — through burnout, not raw counts.** Perceived
  workload is moderately related to burnout and turnover intention (Paul, 2021 —
  QIC-WD umbrella synthesis; Lushin et al., 2023), and burnout erodes job satisfaction
  longitudinally (Lizano & Mor Barak, 2015), with organizational resources acting
  protectively (He et al., 2018). Notably, the best meta-analysis finds *objective*
  caseload size alone does not significantly predict turnover intention (Kim & Kao,
  2014) — which is precisely the argument for weighted workload over case counts: the
  weight approximates the perceived-demand construct that actually predicts outcomes.
  California's SB 2030 workload study (American Humane Association & Walter R. McDonald
  & Associates, 2000, for CDSS) remains the canonical demonstration that mandated
  workloads exceeded the time available — the state funded roughly one-third of the
  resources needed for mandated activities. Federal turnover context: median caseworker
  tenure ≈ 1.8 years and median state turnover 14–22% annually (Edwards & Wildeman,
  2018, AFCARS 2003–2015).
- **Worker discontinuity is consistently associated with worse child outcomes — the
  association is robust, the causal magnitude is not established.** The widely cited
  Milwaukee review (Flower, McDonald, & Sumski, 2005) reported permanency falling
  steeply with each additional assigned worker, but it is unpublished descriptive gray
  literature with a built-in time-at-risk confound; the current scoping review
  (MacLochlainn et al., 2026) finds the association consistent across four decades of
  studies while judging the causal evidence base thin. Stronger recent evidence targets
  the *mechanisms*: worker practice quality degrades before departure net of case
  characteristics (Hoffmeister, 2026), post-reunification worker contact reduces reentry
  (Ahn et al., 2025), worker count is associated with slower permanency in multivariate
  models (Ryan et al., 2006), and youth describe disengagement after worker changes
  (Strolin-Goltzman et al., 2010).
- **Worker capability plausibly affects outcomes.** Children with MSW-level workers
  spent ~5 months less in care in Illinois administrative data (Ryan et al., 2006);
  worker education and supervision are associated with stronger family engagement and
  alliance (Cheng & Lo, 2018). Critical-incident reviews routinely surface cases whose
  dynamics exceeded a novice worker's preparation; rotation-based assignment makes such
  mismatches a matter of chance.
- **Concentration of severe cases is a distinct hazard from total load.** The share of
  trauma-heavy cases in a caseload predicts secondary traumatic stress more strongly
  than case volume (Hensel et al., 2015, meta-analysis; child welfare bridge: Sprang et
  al., 2011; Barbee et al., 2023), and case severity predicts worker departure (Kothari
  et al., 2021). When the most capable workers reliably absorb the hardest cases, the
  agency taxes competence — and case-mix, not just caseload, must be managed
  (see Doc 04 §4.3's severe-share cap).

## 1.2 What adjacent fields have solved — and what remains unproven

The matching problem is not novel in structure; child welfare is late to it. But the
precedents must be characterized honestly:

- **Nursing acuity systems** assign patients to nurses using acuity scores and nurse
  competency levels, with unit-level balancing — the closest *structural* analogue to
  CASE-MATCH, including the safety-floor logic. The evidence status matters, though:
  staffing *levels* clearly affect outcomes (Aiken et al., 2002), but systematic reviews
  find the evidence for acuity-based staffing *tools* themselves "highly limited," with
  no particular tool empirically favored and benefits confounded with added staff
  (Griffiths et al., 2020; Twigg et al., 2021). The analogue is structurally
  established and empirically unproven at the assignment level — which is exactly the
  gap this framework's evaluation phase (Doc 06) is designed to close. The nurse–patient
  assignment *optimization* literature is directly citable (Mullinax & Lawley, 2002;
  Punnakitikashem et al., 2008; Sir et al., 2015 — whose acuity-plus-perceived-workload
  MILP is the closest published analogue).
- **Weighted caseload models in courts, probation, and public defense** (Flango &
  Ostrom, 1996; Kleiman et al., 2017; Pace et al., 2023 — the RAND national public
  defense workload study) established the two-track methodology CASE-MATCH borrows for
  case-weight calibration: time studies regressing logged effort on case attributes,
  adjusted by structured expert review.
- **Assignment optimization** is a mature area of operations research (Burkard et al.,
  2009; Pentico, 2007); the special structure here (small per-unit worker pools,
  lexicographic objectives, online arrivals, transfer penalties) is well within routine
  solver capability.
- **Within child welfare itself, prior optimization work exists and this framework
  builds beside it.** Baron et al. (2024) apply mechanism design to CPS *investigator*
  assignment, replacing rotational queues, with simulated reductions of up to 14% in
  unnecessary placements; adjacent work allocates homelessness services by predicted
  outcomes (Kube et al., 2019) and studies foster-care matching-market design
  (Highsmith, 2024); several states run workload-based staff *allocation* tools
  (Washington DCYF, 2023). CASE-MATCH differs on the axis that matters for governance:
  those approaches optimize against *predicted case outcomes*, while CASE-MATCH matches
  *measured* case demands to *measured* worker capability and capacity, and never
  predicts family outcomes. The framework's specific contribution is therefore: the
  first **measurement layer on both sides of the match** (a validated complexity
  instrument and a workforce capability instrument), the **governance layer**, and a
  prospective evaluation design — not the optimizer itself.

## 1.3 Positioning: this is not a predictive risk model

Algorithmic tools in child welfare are controversial primarily where they **score
families** — predictive risk models such as the Allegheny Family Screening Tool have
drawn sustained scrutiny over disparate impact, transparency, and due process
(Chouldechova et al., 2018; Eubanks, 2018; subsequent ACF and academic commentary).
CASE-MATCH is deliberately on the other side of the desk:

| | Predictive risk models | CASE-MATCH |
|---|---|---|
| Scores | Families (probability of future harm) | The *work* a case requires; the *capability* of staff |
| Decision influenced | Screening/removal decisions about families | Which employee is assigned to do the work |
| Adverse action possible | Yes (against families) | No family-facing decision; worker-facing use is governed (see Doc 05) |
| Failure mode | False positives harm families | Poor match → caught by supervisor override + monitoring |

This positioning is not a shield against all governance obligations — worker-side
fairness, family-side equity monitoring, and transparency are treated fully in
Doc 05 — but it materially changes the risk profile and the appropriate oversight
regime. Two 2026 realities sharpen it (details in Doc 05 §5.7 and Doc 07 §7.9): the
operative federal guidance is now OMB M-25-21, whose "high-impact AI" test CASE-MATCH
analyzes explicitly rather than asserting exemption; and ACF now actively encourages
predictive analytics in child welfare under human-in-the-loop, workforce-capacity, and
transparency conditions — so CASE-MATCH is best understood not as a rival to predictive
risk models but as the *workforce-side infrastructure* those conditions presuppose,
while keeping its bright line: it never scores families. The empirical record on the
AFST cuts both ways and is cited both ways: overrides by workers improved racial equity
(Cheng et al., 2022), the tool plus discretion reduced disparities (Rittenhouse et al.,
2026), and the civil-rights scrutiny it drew (AP, 2022–2023; Gerchick et al., 2023) is
the reason CASE-MATCH's family-facing line exists.

## 1.4 Why decision support, not automation

CASE-MATCH recommends; supervisors decide. This is a considered design choice, not a
hedge:

1. **Supervisors hold information the model cannot.** Team dynamics, a worker's
   unrecorded personal circumstances, a family's history with a specific worker — the
   override channel is how that information enters the system.
2. **Trust is the adoption constraint.** Workload tools in child welfare fail through
   disuse, not inaccuracy. A recommender that explains itself and visibly yields to
   supervisor judgment builds the usage base that later, more automated modes require.
3. **Overrides are the model's best training data.** Every override with a reason code
   is a labeled disagreement between model and expert — the core input to calibration
   review (Doc 06, Phase D).

## 1.5 The three-level structure

The user of this framework is not one decision-maker but three nested ones, and the
model is explicitly multi-level:

- **Individual level.** For a given case, which worker? The match-quality function
  (Doc 04, §4.2) scores each feasible worker–case pair on skill–need alignment,
  experience tier, continuity, logistics, and bounded developmental stretch.
- **Supervisor / unit level.** A supervisor manages a unit of roughly 5–8 workers.
  At this level the questions are: is my unit's *skill coverage* adequate for my unit's
  *case-need profile*? Is weighted workload equitable? Do stretch assignments fit my
  supervision capacity? The unit is also the natural cluster for the pilot (Doc 06).
- **Agency level.** Across units and offices: routing of cases when a unit is
  infeasible; aggregate skill-gap analysis (which competencies, if trained, would
  relieve the most binding constraints — recoverable directly from the optimizer's
  shadow prices, §4.6); hiring-profile guidance; and cross-office equity monitoring.

## 1.6 Design principles (normative commitments)

The seven principles listed in the README are normative commitments with operational
teeth; each maps to a specific mechanism:

| Principle | Mechanism |
|---|---|
| Safety before efficiency | Lexicographic level L1 (skill floors) precedes match quality and equity (Doc 04 §4.3) |
| Complexity earns capability | Asymmetric gap penalty: skill shortfall penalized ~3× surplus (Doc 04 §4.2) |
| Weighted caseload | All capacity constraints in calibrated workload points (Doc 02 §2.5; Doc 03 §3.4) |
| Continuity is expensive | Transfer penalty τ scaled by relationship duration and stage; milestone lockouts (Doc 04 §4.5) |
| Workers develop | Bounded stretch term coupled to supervision-capacity constraint (Doc 03 §3.5; Doc 04 §4.2) |
| Humans decide | Top-3 recommendations with component-level explanations; override with reason codes (Doc 04 §4.7) |
| Rigor on both sides | Psychometric plan for CCI and WCP with reliability/validity targets (Doc 06 Phase A) |

## 1.7 Scope and assumptions

- **Setting:** generic U.S. public child welfare agency (county- or state-administered),
  covering the full continuum: intake/investigation, ongoing in-home services, ongoing
  out-of-home services, and permanency-focused work. Stage differences are handled via
  stage multipliers and stage-specific caseload standards, not separate models.
- **Data assumptions:** none beyond what agencies typically hold — SACWIS/CCWIS case
  records, HR and training records, and supervisor knowledge. Both instruments are
  designed with explicit crosswalks so agencies with SDM/CANS can pre-populate.
- **Out of scope (this version):** hotline screener assignment; foster-home matching
  (a distinct matching problem); private-agency contracted case management; supervisor–
  worker matching (flagged as an extension in Doc 04 §4.8).

## 1.8 References

All citations in this framework were verified against primary or authoritative sources
in July 2026; the consolidated, verified reference list — with DOIs/URLs, gray-literature
flags, and verification caveats — is maintained in [references.md](references.md). The
assumption-by-assumption evidence review is in
[07-literature-synthesis.md](07-literature-synthesis.md).
