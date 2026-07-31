# 2. The Case Complexity Index (CCI)

The CCI measures **what a case demands of the worker who carries it** — in skill, in
time, and in emotional and logistical load. It is *not* a risk assessment: two cases can
carry identical maltreatment risk while demanding very different work. The CCI produces
two outputs used by the matching layer:

1. a **domain profile** `c = (c₁ … c₇)` — the case's needs by domain, matched against
   worker skills; and
2. a **scalar case weight** `w(c)` in **workload points (WLP)** — the case's expected
   consumption of worker capacity, used in all caseload accounting.

**Design precedent.** No validated case-*complexity* instrument distinct from risk
exists in child welfare (a 2024 *BJSW* review finds complexity discussed but essentially
unmeasured), but one exists in general health care: **INTERMED** (Huyse et al., 1999;
de Jonge et al., 2005), a multi-domain biopsychosocial complexity index with 0–3
anchored items and interrater r = .91–.96, explicitly distinct from illness severity.
The CCI mirrors its design logic — anchored multi-domain rating, complexity ≠ risk —
and its validation sequence (Doc 06, Phase A).

## 2.1 Design requirements

- **Ratable in ≤ 10 minutes** by the screening or transferring worker from information
  already gathered, with supervisor confirmation at assignment.
- **Behaviorally anchored** 0–3 ratings per domain (following the CANS "action-level"
  convention — Lyons, 2009; reliability precedent: Anderson et al., 2003 — with the
  caveat that independent CANS psychometric evidence is thinner than its adoption
  suggests (Brown et al., 2022), so the CCI runs its own full validation rather than
  importing CANS's: 0 = no need for special attention; 1 = watch/mild; 2 = clearly
  elevates the work; 3 = dominates the work / requires specialized capability).
- **Crosswalkable**: every domain lists which SDM, CANS, and standard SACWIS/CCWIS
  fields can pre-populate or inform the rating, so agencies with structured assessments
  start warm rather than cold. Crosswalks lean on the SDM actuarial *risk* scales,
  which have comparative validity evidence (Baird & Wagner, 2000; Johnson, 2011); the
  SDM *safety* assessment is much more weakly validated (McNellan et al., 2022) and is
  used as contextual input only, never as a validity anchor.
- **Dynamic**: complexity is re-scored on defined triggers (§2.6); the case weight and
  profile in the optimizer are always the current ones.

## 2.2 The seven domains

### D1 — Safety and risk intensity
The degree to which active safety threat management dominates the work: severity and
chronicity of allegations, active safety plan requiring monitoring, prior substantiated
reports, violence directed at professionals.
*Crosswalk: SDM safety assessment result, SDM risk level, allegation type/severity,
prior-report count.*
- 0: no active safety threat management beyond standard contacts.
- 1: resolved or well-controlled safety concerns; routine monitoring.
- 2: active safety plan requiring frequent verification; volatile but engageable household.
- 3: ongoing serious threat dynamics (e.g., coercive control, threats to staff, near-fatality history) requiring advanced safety practice.

### D2 — Child needs intensity
Behavioral health, medical fragility, developmental disability, education disruption,
and age-band demands (infants and older adolescents both raise the floor).
*Crosswalk: CANS child-needs domains; regional-center/DD eligibility; medical-care plan
flags; placement-in-psychiatric-setting history.*
- 0–3 anchored from "typical developmental needs" to "medically fragile or acute
  behavioral health needs requiring specialized coordination" (rate the *highest-need
  child* on the case; sibling-group size is captured in D3).

### D3 — Family system complexity
Number of children and households; caregiver mental illness, substance use, domestic
violence; housing instability/homelessness; criminal-justice involvement; non-resident
parents requiring search and engagement.
*Crosswalk: CANS caregiver domains; SDM risk items; household composition records.*

### D4 — Legal and procedural complexity
Court posture and procedural load: contested hearings, termination-of-parental-rights
proceedings, **ICWA** application (inquiry, notice, active efforts, QEW requirements),
interstate placements (**ICPC**), immigration-related complications, concurrent
planning, competing-jurisdiction issues.
*Crosswalk: court-hearing schedule, ICWA-eligibility flags, ICPC referrals.*
- A case with ICWA application scores minimum 2 on D4 and generates a **credential
  requirement** (§2.4), not merely a score.

### D5 — Service coordination load
Number and difficulty of systems the worker must actively coordinate: behavioral-health
providers, schools/IEPs, probation, regional center/DD services, public benefits,
housing programs, tribes, immigration counsel.
- Anchors keyed to *count of actively coordinated systems* (0: ≤1; 1: 2–3; 2: 4–5;
  3: ≥6 or any two systems in active conflict).

### D6 — Relational and engagement demands
What it takes to build and keep a working alliance: family hostility or sustained
disengagement; history of failed worker relationships; language access needs (also a
credential requirement when interpretation is not a substitute, e.g., therapeutic
engagement in-language); geographic distance / travel burden; media or political
attention on the case.

### D7 — Stage-specific procedural tempo
The clock the case runs on: investigation response timelines, monthly-contact minimums
across placements, court-report cycles, permanency-hearing timelines. Rated within
stage; the *between*-stage difference is carried by the stage multiplier (§2.5), so D7
captures tempo variation among cases at the same stage (e.g., three placements in three
counties vs. one local placement).

## 2.3 Scoring rules

- Each domain rated 0–3 with written anchors; rater selects the anchor, not a number.
- **Complexity tier** `T(c) ∈ {T1…T4}` summarizes the profile for floors and reporting:
  - **T4 (critical)**: any domain = 3 on D1, or two or more domains = 3, or total ≥ 15.
  - **T3 (high)**: any domain = 3, or total 11–14.
  - **T2 (moderate)**: total 6–10.
  - **T1 (routine)**: total ≤ 5.
- Dual rating at assignment: proposing worker rates, receiving supervisor confirms;
  disagreements ≥ 2 points on any domain are resolved in conference and logged (this
  disagreement stream is the ongoing inter-rater reliability sample, Doc 06 §A.3).

## 2.4 Credential requirements (hard flags, not scores)

Some case attributes generate **requirements** `R(i)` that a worker must satisfy for the
assignment to be feasible at all — these bypass scoring and become L0 constraints
(Doc 04 §4.3):

- ICWA-active case → ICWA-qualified practice (per agency/tribal-agreement standard);
- primary family language → worker proficiency or approved interpretation plan
  (agency policy decides which needs are proficiency-mandatory);
- commercially sexually exploited child (CSEC) → CSEC-trained worker;
- medically fragile child → medical-case-management training;
- plan-of-safe-care infant → relevant certification where policy requires;
- conflict-of-interest exclusions (worker knows family, prior conflict, dual
  relationship) → specific-worker exclusions.

The requirement taxonomy is agency-configurable; the framework fixes the *mechanism*.

## 2.5 From profile to case weight: `w(c)` in workload points

The scalar weight converts complexity into expected capacity consumption:

```
w(c) = m_stage × ( b_stage + Σ_d β_d · c_d )
```

- `b_stage`: base weight of a minimally complex case at that stage;
- `β_d`: per-domain marginal weights, **calibrated empirically from a time study**
  (random-moment sampling or structured diaries; Doc 06 §A.4) by regressing logged case
  hours on domain scores, then adjusted by structured expert review — the two-track
  (time study + Delphi) method that is standard in weighted-caseload practice (Flango &
  Ostrom, 1996; Pace et al., 2023; live child welfare implementations: Washington DCYF,
  2023; Wisconsin DCF, 2021) — not set by committee alone;
- `m_stage`: stage multiplier {investigation, ongoing in-home, ongoing out-of-home,
  permanency/TPR} reflecting stage-level tempo differences.

Until an agency runs its own time study, the framework ships **provisional weights**
derived from published weighted-caseload studies (SB 2030; NCSC methodology), clearly
flagged as priors to be replaced. One workload point is normalized so that a full-time
ongoing worker's monthly capacity ≈ 100 WLP (Doc 03 §3.4), making utilization percentages
directly readable.

**Design note — separability.** The linear form is a deliberate first choice: it is
auditable, calibratable with modest data, and each `β_d` is interpretable. Interaction
terms (e.g., D1×D6: hostile *and* dangerous) are an evaluated extension in Phase A, added
only if the time-study regression shows material lack of fit.

## 2.6 Re-scoring triggers

The CCI is re-scored (same dual-rating procedure) on:

1. stage change (investigation → ongoing; in-home → out-of-home; case-plan goal change);
2. court events that change posture (detention, adjudication, TPR filing, contested
   hearing set);
3. placement change or new placement in another jurisdiction;
4. critical incident on the case;
5. scheduled review — every 90 days without another trigger;
6. supervisor discretion, always.

Weight changes flow into the capacity ledger immediately; a re-score never by itself
triggers reassignment (reassignment is only proposed in rebalancing runs, with the
continuity penalty applied — Doc 04 §4.5).

## 2.7 Measurement risks and the anti-gaming operating procedure

- **Complexity–demography confounding.** Poverty-linked items (housing instability,
  systems involvement) will correlate with race and class — system contact itself is
  pervasive and racially unequal (Kim et al., 2017; Putnam-Hornstein et al., 2021), by
  some combination of differential exposure and residual bias (Drake et al., 2011;
  Dettlaff et al., 2011). In CASE-MATCH the *effect* of a higher score is a more capable
  worker and a lower-count caseload for that worker — an equity-positive direction — but
  scoring disparities are still audited (Doc 05 §5.3) because miscalibrated scores
  distort workload accounting and could stigmatize.
- **Gaming and drift are documented phenomena, not hypotheticals.** Indicators that
  carry resource consequences corrupt the processes they measure (Campbell, 1979); DRG
  "upcoding" is the canonical demonstration (Silverman & Skinner, 2004); nursing acuity
  systems show chronic reliability decay in operation (Fasoli & Haddock, 2010); and
  child welfare workers demonstrably adjust and subvert SDM scores in practice (Bosk,
  2018). The CCI therefore builds the countermeasures into its operating procedure:
  1. **Standing blind double-rating audit** — each quarter, a random ~5% of active
     cases is independently re-rated by a rater outside the unit (the audit model shown
     to preserve acuity-system reliability in nursing: Junttila et al., 2023);
     audit-vs-operational drift is a standing steering-body report.
  2. **Drift triangulation** — score distributions by office and rater, checked against
     periodic time-study re-checks; rising scores without rising logged hours is the
     upcoding signature (Doc 06 §D).
  3. **Dual rating at assignment** with logged disagreements (§2.3) as the live
     reliability stream.
- **Rater burden.** Every added item costs adoption; the instrument stays at seven
  domains and one screen.
