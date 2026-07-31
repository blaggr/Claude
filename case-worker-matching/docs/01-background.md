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
studied directly:

- **Caseload size and weight predict worker outcomes.** Excessive caseloads are among
  the most consistently reported drivers of burnout, secondary traumatic stress, and
  turnover intention in child welfare (GAO, 2003; Lizano & Mor Barak, 2015; NCWWI
  workforce reports). California's SB 2030 workload study (2000) remains the canonical
  demonstration that mandated workloads exceeded the time available to perform even
  minimum statutory activities.
- **Turnover damages children's outcomes.** The frequently cited Milwaukee analysis
  (Flower, McDonald, & Sumski, 2005) found that the probability of achieving permanency
  within the study window fell dramatically with each additional worker assigned to a
  case; subsequent work (e.g., Ryan et al., 2006; Edwards & Wildeman, 2018 on caseworker
  instability) supports the general finding that worker discontinuity delays permanency
  and disrupts family engagement.
- **Skill–demand mismatch is a hidden safety issue.** Critical-incident reviews
  routinely surface cases where a novice worker carried a case whose dynamics (coercive
  control, medical complexity, sophisticated caregiver presentation) exceeded what their
  training and supervision prepared them to see. Rotation-based assignment makes such
  mismatches a matter of chance.
- **Inequitable distribution of hard cases drives attrition of exactly the workers
  agencies most need.** When the most capable workers reliably absorb the hardest cases
  without capacity adjustment, the agency taxes competence — a pattern workers name in
  exit interviews.

## 1.2 What adjacent fields have solved

The matching problem is not novel in structure; child welfare is late to it.

- **Nursing acuity systems** assign patients to nurses using patient acuity scores and
  nurse competency/experience levels, with unit-level balancing — the closest structural
  analogue to CASE-MATCH, including the safety-floor logic (a high-acuity patient must
  get a nurse above a competence threshold).
- **Weighted caseload models in courts and probation** (e.g., National Center for State
  Courts weighted caseload studies) established the methodology CASE-MATCH borrows for
  case-weight calibration: time studies regressing logged effort on case attributes.
- **Assignment optimization** is a mature area of operations research; the special
  structure here (small per-unit worker pools, lexicographic objectives, online arrivals,
  transfer penalties) is well within routine solver capability. The contribution of this
  framework is not the optimizer; it is the **measurement layer** and the **governance
  layer** that make optimization legitimate and useful in a child welfare context.

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
Doc 05 — but it materially changes the risk profile and the appropriate oversight regime.
It also aligns with federal guidance trends (OMB M-24-10 and successors on public-sector
AI; ACF's guidance on responsible use of technology in child welfare) that distinguish
rights-impacting from operations-supporting uses.

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

## 1.8 References (indicative; verify before formal use)

- Chouldechova, A., Benavides-Prado, D., Fialko, O., & Vaithianathan, R. (2018). A case
  study of algorithm-assisted decision making in child maltreatment hotline screening.
  *PMLR (FAT\*)*.
- Edwards, F., & Wildeman, C. (2018). Characteristics of the front-line child welfare
  workforce. *Children and Youth Services Review*.
- Eubanks, V. (2018). *Automating Inequality*. St. Martin's Press.
- Flower, C., McDonald, J., & Sumski, M. (2005). *Review of turnover in Milwaukee County
  private agency child welfare ongoing case management staff*. Bureau of Milwaukee Child
  Welfare.
- GAO (2003). *Child welfare: HHS could play a greater role in helping child welfare
  agencies recruit and retain staff* (GAO-03-357).
- Lizano, E. L., & Mor Barak, M. (2015). Job burnout and affective wellbeing: A
  longitudinal study of burnout and job satisfaction among public child welfare workers.
  *Children and Youth Services Review*.
- California Legislature (2000). *SB 2030 Child Welfare Services Workload Study*
  (American Humane Association for CDSS).
- Ryan, J. P., Garnier, P., Zyphur, M., & Zhai, F. (2006). Investigating the effects of
  caseworker characteristics in child welfare. *Children and Youth Services Review*.
- Child Welfare League of America. *Standards of excellence for services* (caseload
  guidance); NCSC weighted caseload methodology reports; NCWWI workforce development
  literature.
