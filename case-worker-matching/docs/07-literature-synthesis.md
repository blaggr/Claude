# 7. Literature Synthesis: Evidence Review of the Model's Assumptions

This section reports a structured literature review of every load-bearing assumption in
the CASE-MATCH framework, conducted July 2026. Every citation was verified against
primary or authoritative sources (publisher DOI records, agency websites, PubMed,
Google Scholar); verification status is noted where it matters, and the consolidated
reference list is in [references.md](references.md). Where the evidence contradicts or
complicates an assumption, that is stated plainly; the resulting design changes are in
[08-model-revisions.md](08-model-revisions.md).

Summary of verdicts:

| # | Assumption | Verdict |
|---|---|---|
| A1 | Caseload size drives burnout and turnover | **Split**: workload→burnout→turnover-intention supported; *objective* caseload→turnover not supported meta-analytically |
| A2 | Worker discontinuity harms permanency (transfer penalty) | **Directionally supported, not causally quantified**; key statistic is confounded gray literature |
| A3 | Worker skill/experience affects case outcomes | Supported (observational) |
| A4 | Weighted caseload > raw counts | **Strongly supported**; now the mainstream position |
| A5 | Nursing acuity assignment is an evidence-backed analogue | **Overstated**: structurally established, empirically unproven |
| A6 | CANS/SDM conventions justify the CCI design | **Qualified**: sound templates, weaker psychometric warrant than assumed |
| A7 | The framework's novelty (no prior assignment optimization in CW) | **Wrong as stated**: prior work exists and must be cited |
| A8 | Stretch assignments develop workers if gated | **Supported**, including the gating specifically |
| A9 | Supervision moderates worker outcomes | Supported (meta-analytic) |
| A10 | Policy alignment via OMB M-24-10 | **Obsolete**: rescinded April 2025; landscape reversed |
| A11 | Override-rate band (near-0% bad, >30% bad) | **Half right**: the upper bound contradicts field evidence |
| A12 | Complexity–demography confound needs auditing | Supported; evidence chain strengthened |
| A13 | Stepped-wedge pilot design and power sketch | Design supported; **power method needs correction** |

## 7.1 A1 — Caseload and worker outcomes: the assumption must be split

The framework claimed caseloads drive "burnout, secondary traumatic stress, and
turnover." The verified evidence supports a more specific causal chain and one
important negative finding:

- **Supported:** perceived workload is moderately related to burnout and turnover
  *intention* (Paul, 2021 — the QIC-WD umbrella synthesis); work-intensity burden showed
  the strongest association with intent to leave in a recent 258-worker survey (Lushin
  et al., 2023); high demands relate to burnout with organizational resources acting
  protectively, per the Job Demands–Resources framing (He et al., 2018); burnout erodes
  job satisfaction and affective well-being longitudinally (Lizano & Mor Barak, 2015 —
  which measures burnout and satisfaction, *not* turnover, and is now cited only for
  that).
- **Not supported:** the best meta-analysis of turnover-intention predictors (Kim & Kao,
  2014; 22 studies) found **objective caseload size had no significant effect** —
  stress, emotional exhaustion, organizational commitment, and job satisfaction
  dominate. The workload–outcomes literature also rests almost entirely on *perceptual*
  measures rather than administrative case counts.
- **Consequence for the model:** caseload balancing is justified as managing the
  *demands* side of a demands–resources system whose effects run through perceived
  workload and burnout — not as a direct turnover lever. This is, properly understood,
  an argument *for* the weighted-workload approach: if raw counts don't predict
  outcomes but perceived workload does, then a weight that captures what cases actually
  demand is the better proxy for the construct that matters. The framework now makes
  that argument explicitly rather than assuming counts matter per se.
- Secondary traumatic stress is related to but distinct from workload-driven burnout
  (Rienks, 2020) and is addressed under A8/case-mix below.

Verification notes: GAO-03-357 confirmed (corporate author is the U.S. *General
Accounting* Office, its name until 2004). The SB 2030 study was conducted **jointly** by
the American Humane Association and Walter R. McDonald & Associates for the California
Department of Social Services (2000); it covered 13,584 county staff and found the state
funded roughly one-third of the resources needed for mandated activities. CWLA's
standards are program-specific — 12 active investigations/month, **15–17 families** for
ongoing in-home services, 12–15 children for family foster care — date to decades-old
Standards of Excellence editions, and CWLA itself now states "a number is not
sufficient," recommending local workload studies. The framework's earlier "12–15
ongoing" shorthand was imprecise and is corrected.

## 7.2 A2 — Continuity and the transfer penalty: directionally right, not causally quantified

The transfer penalty (L4) leaned on Flower, McDonald & Sumski (2005). Verification
findings:

- The report is real (an unpublished January 2005 management review for the Bureau of
  Milwaukee Child Welfare) and the famous statistics — 74.5% permanency with one
  worker vs. 17.5% with two, falling toward ~0.1% at six or seven workers — are
  faithfully quoted by secondary sources. But it is **descriptive gray literature with
  no multivariate controls and a fixed 21-month observation window**, which builds in a
  time-at-risk confound: children who exit quickly *mechanically* accumulate fewer
  workers. No causal replication of those magnitudes exists. The most current synthesis
  (MacLochlainn et al., 2026 — an 11-study scoping review spanning four decades)
  concludes turnover is consistently *associated* with placement disruption, permanency
  delay, and distress, while explicitly judging the causal evidence base thin and dated.
- Endogeneity runs in both directions: severe cases both accumulate more workers and
  drive workers to quit (Kothari et al., 2021), so any worker-count/permanency
  correlation is partly case-difficulty confounding.
- The **mechanism** evidence is stronger than the magnitude evidence: practice quality
  measurably degrades as workers approach departure, net of case characteristics and
  fixed effects (Hoffmeister, 2026, Wisconsin administrative data); caseworker
  visitation after reunification reduces reentry hazard (Ahn et al., 2025); youth
  describe re-telling their stories and disengaging after worker changes
  (Strolin-Goltzman et al., 2010); the association survives multivariate controls in
  Ryan et al. (2006).
- **Consequence for the model:** the transfer penalty stays, but (i) it is documented
  as encoding a robust observational association plus mechanism evidence — not a causal
  effect size; (ii) its magnitude is a tunable policy parameter subject to sensitivity
  analysis, never "calibrated" to the Flower et al. percentages; (iii) its functional
  form is revised to diminishing marginal penalty (the first transfer is the worst),
  which fits the relationship-disruption mechanism better; and (iv) any future
  data-driven calibration must control for case complexity and duration or it will
  attribute case-difficulty harm to transfers. See §8.2.

Citation hygiene adopted: Edwards & Wildeman (2018) is cited only for workforce
*prevalence* (median caseworker tenure ≈ 1.8 years; median annual caseload ≈ 55
children; median state turnover 14–22%/year from AFCARS 2003–2015) — it tests no
outcome effects. Ryan et al. (2006) carries the worker-count and MSW-effect claims.

## 7.3 A3 — Worker capability and outcomes

Ryan et al. (2006) remains the anchor: children with MSW-level caseworkers spent ~5
months less in care (Illinois administrative data, multilevel models). Cheng & Lo
(2018) links worker education, supervision, and diversity training to stronger family
engagement and therapeutic alliance — the mechanism by which capability should
translate into outcomes. All observational; the framework's Phase C pilot is the right
response, and its exploratory child-outcome measures now include worker-change counts
explicitly.

## 7.4 A4 — Weighted caseload: the strongest-supported assumption

Time-study-calibrated workload is now the mainstream position across three literatures:
the NCSC weighted-caseload lineage in courts (Flango & Ostrom, 1996; Kleiman et al.,
2017; a 2024 Vermont application), the RAND national public defense workload study
(Pace et al., 2023 — Delphi plus time-study calibration, the strongest recent
methodological precedent), current federal child welfare guidance (Child Welfare
Information Gateway, 2022 — which formalizes the caseload/workload distinction), and
live state implementations built on random-moment time studies (Washington DCYF, 2023;
Wisconsin DCF, 2021). The framework's calibration design (Doc 02 §2.5) now cites the
two-track precedent: time-study regression as primary, structured expert review
(Delphi) as adjustment — matching how courts and public defense actually set weights.

## 7.5 A5 — The nursing analogue: structurally established, empirically unproven

Aiken et al. (2002) is solid but is evidence about staffing *levels* (each additional
patient per nurse: +7% 30-day mortality odds, +23% burnout odds), not about
acuity-matched *assignment*. The authoritative review of staffing methodologies and
tools (Griffiths et al., 2020) concludes evidence on the tools themselves is "highly
limited," no particular tool is empirically favored, different tools produce very
different staffing estimates, and observed benefits mostly trace to added staff rather
than smarter allocation; Twigg et al. (2021) found 21 of 22 studies in their review
concerned mandated ratios, not acuity tools. Patient-classification systems also have
chronic reliability-maintenance problems in operation (Fasoli & Haddock, 2010), with
ongoing parallel-rating audits required to keep them honest (Junttila et al., 2023).

**Consequence:** the framework now presents nursing as a *structural* precedent whose
assignment-level effectiveness is unproven — which is precisely the gap the Phase C
trial addresses — and imports the operational lesson (standing double-rating audits)
into the CCI's design. The nurse–patient assignment OR literature is real and citable:
Mullinax & Lawley (2002 — *Journal of the Operational Research Society*, a venue
correction from the earlier draft), Punnakitikashem et al. (2008), and Sir et al.
(2015), whose MILP calibrated to nurses' perceived workload is the closest published
analogue to CASE-MATCH's design.

## 7.6 A6 — Instrument conventions: sound templates, thinner warrant than assumed

- **CANS:** the 0–3 action-level convention is properly cited to Lyons (2009), with
  peer-reviewed reliability from Anderson et al. (2003; interrater .72–.85). But an
  independent review (Brown et al., 2022) finds published psychometric evidence
  surprisingly thin given the tool's adoption, with much of the reliability record in
  vendor gray literature — and Lyons himself frames communimetrics as an *alternative*
  to classical psychometrics. The CCI therefore borrows the *structure* while running
  its own full validation (Phase A), as planned.
- **SDM:** the actuarial *risk* scales have genuine comparative validity evidence
  (Baird & Wagner, 2000; Johnson, 2011 — a prospective field study), but the *safety*
  assessment is much more weakly validated (McNellan et al., 2022, systematic scoping
  review), and field studies show workers adjust and subvert SDM scores in practice
  (Bosk, 2018). The CCI crosswalk now leans on the risk scales only, and Bosk's finding
  is treated as direct evidence for the CCI's anti-gaming design.
- **BARS:** the classic origin (Smith & Kendall, 1963) is correct, but decades of
  psychometric comparisons show anchored formats do not reliably outperform simpler
  scales (Schwab et al., 1975; Landy & Farr, 1980 — rating quality lives in rater
  training and cognition, not format). The honest case for BARS is transparency,
  job-relevance, feedback utility, and rater acceptance (Jacobs et al., 1980). The WCP
  is repositioned accordingly: anchors for legitimacy and contestability, reliability
  investment in rater training, calibration sessions, and audits. See §8.4.
- **A direct precedent exists and is now cited:** INTERMED (Huyse et al., 1999;
  de Jonge et al., 2005) is a validated, multi-domain, 0–3-anchored *biopsychosocial
  complexity* instrument — explicitly distinct from illness severity/risk, with
  interrater r = .91–.96. It is the closest existing template for the CCI, and the
  CCI's honest novelty claim is "no validated *case complexity* instrument distinct
  from risk exists *in child welfare*," not that complexity measurement is unprecedented.
- **Gaming:** the risk is not hypothetical — Campbell's law (Campbell, 1979), DRG
  upcoding (Silverman & Skinner, 2004), acuity-system drift (Fasoli & Haddock, 2010),
  and SDM score adjustment (Bosk, 2018). Mitigations move from a "known risks" footnote
  into the instrument's operating procedure (§8.3).
- **Thresholds:** κ ≥ .60 (Landis & Koch, 1977) and ICC(2,1) ≥ .75 (Cicchetti, 1994;
  Koo & Li, 2016 — who caution .75 is only the floor of "good") stand. The content-
  validity criterion is corrected from a flat CVI ≥ .80 to **I-CVI ≥ .78 and
  S-CVI/Ave ≥ .90** per Polit & Beck (2006; Polit, Beck & Owen, 2007), with the
  computation method specified.

## 7.7 A7 — Novelty: prior work exists and is now cited

The claim that assignment is "the last unsystematized decision" was too strong.
Verified prior work:

- **Baron, Lombardo, Ryan, Suh & Valenzuela-Stookey (2024, NBER WP 32369)** directly
  studies reassignment of CPS *investigators* away from rotational queues using
  mechanism design; simulations suggest up to 14% fewer unnecessary foster-care
  placements. This is the most important adjacent work and differs from CASE-MATCH on
  every axis that matters for positioning: it optimizes investigator assignment against
  *predicted case outcomes*, where CASE-MATCH matches measured case demands to measured
  worker capability and capacity under safety, equity, and continuity constraints — a
  workforce-measurement approach rather than an outcome-prediction approach.
- Kube, Das & Fowler (2019) allocate homelessness services via counterfactual
  prediction (adjacent precedent); Highsmith (2024, preprint) studies foster-care
  matching-market design; several states operate workload-based staff *allocation*
  tools (Washington DCYF, 2023; Colorado DHS).

**The defensible novelty claim, adopted in §8.1:** no prior *prospectively evaluated*
system that matches measured case complexity to measured worker capability under
weighted-capacity, safety-floor, equity, and continuity constraints, with a validated
measurement layer on both sides of the match. The framework also gains a literature to
sit in: algorithmic work *allocation* and its fairness (Lee et al., 2015; Uhde et al.,
2020; Ammitzbøll Flügge et al., 2021), including the caution that allocation algorithms
under scarcity can concentrate inequality (Moon & Guha, 2026).

## 7.8 A8 — Stretch, supervision, and case-mix: supported, with two upgrades

- **Stretch gating is exactly what the literature prescribes.** Developmental challenge
  predicts skill growth with *diminishing returns at high challenge*, offset by feedback
  availability (DeRue & Wellman, 2009); high challenge without self-efficacy/support
  produces emotional exhaustion and disengagement (Courtright et al., 2014); assignment
  quality predicts competency growth conditional on orientation and access (Dragoni et
  al., 2009). Supervisor gating is therefore not a bureaucratic check but the mechanism
  (feedback) that makes stretch developmental. One upgrade adopted: stretch is
  additionally **suppressed when a worker's strain indicators are elevated** (§8.5).
- **Supervision as a budgeted resource** is supported by Mor Barak et al. (2009;
  27-study meta-analysis, N = 10,867): task assistance, social-emotional support, and
  interpersonal interaction relate to worker outcomes at r ≈ .30–.40. Complex and
  stretch assignments draw down precisely those finite supervisory functions.
- **Case-mix, not just case-count, drives secondary traumatic stress.** The Hensel et
  al. (2015) meta-analysis found the **proportion** of trauma cases in a caseload
  (caseload *ratio*) a stronger STS predictor than volume or frequency, with work
  support protective. Bridged to child welfare by Sprang et al. (2011) and Barbee et
  al. (2023 — ~54% of 1,113 surveyed frontline workers at clinical STS levels), this
  motivates a new constraint: a **cap on the share of T4/trauma-heavy cases per
  worker** (§8.5). It also sharpens the equity logic — L3 alone balances total load
  but would happily concentrate all severe cases on one under-utilized expert.
- **A cautionary null:** the QIC-WD portfolio (2023) found the Resilience Alliance STS
  intervention improved coping but did **not** reduce turnover, while competency-based
  selection (−22% leaving risk, Oklahoma) and organizational interventions (Milwaukee
  ARC) did move retention. The evaluation plan now treats STS reduction and retention
  as related but distinct outcomes, and the new-worker ramp is framed as consistent
  with onboarding science (documented practice at Alaska OCS and NYC ACS) rather than
  as a tested intervention.

## 7.9 A10 — Policy alignment: the ground moved

Two findings force a rewrite of Doc 05 §5.7 (now revised):

1. **OMB M-24-10 was rescinded on April 3, 2025**, replaced by M-25-21 (use and
   governance) and M-25-22 (procurement) under E.O. 14179. The rights-impacting /
   safety-impacting taxonomy did not survive; the operative category is **"high-impact
   AI"** — AI whose output is "a principal basis for decisions or actions with legal,
   material, binding, or significant effect" — carrying minimum practices
   (pre-deployment testing, AI impact assessments, ongoing monitoring, human oversight,
   training). The framework keeps its rights/operations distinction as its own analytic
   frame but now performs the high-impact analysis explicitly — including the wrinkle
   that assignment decisions can have *significant effects on employees*, which state
   frameworks (Colorado's consequential-decision list; California CPPA ADMT employment
   prong) treat as significant decisions even when no family-facing decision is made.
2. **The federal posture toward analytics in child welfare flipped between 2024 and
   2026.** ACF now actively encourages predictive risk modeling with
   human-in-the-loop, workforce-capacity, and transparency conditions (ACF/ACYF issue
   brief, March 2026; ACYF-CB-IM-26-03 on CCWIS modernization; $6M state pilot funding,
   June 2026). Positioning CASE-MATCH primarily "against" predictive risk models now
   cuts against the operative guidance. The revised framing: CASE-MATCH is
   *complementary workforce-side infrastructure* — it strengthens exactly the workforce
   capacity ACF's own conditions require — while still distinguishing itself from
   family-risk scoring on civil-rights-exposure grounds (the AFST record: AP
   investigations 2022–2023 and DOJ interest; Gerchick et al., 2023; balanced by
   Rittenhouse, Putnam-Hornstein & Vaithianathan, 2026, finding AFST-plus-discretion
   *reduced* Black–white disparities).

State law is a moving target and is now cited with dates: Colorado's AI Act is in a
limbo window (enforcement suspended; replaced by a narrower ADMT framework effective
January 2027); California's operative instruments for a public deployment are AB 302
(high-risk automated-decision-system inventory) and, binding vendors, the CPPA ADMT
regulations (employment "significant decisions" compliance by January 2027).

## 7.10 A11 — The override band: the field data moved the goalposts

The framework's original health metric — near-0% overrides suggests rubber-stamping,
above ~30% suggests the model "lost the room" — was half right:

- **Near-0% is the genuinely dangerous end**, consistent with the automation-bias
  literature (Skitka et al., 1999) and the workload pressure under which child welfare
  operates. Trained workers *can* catch erroneous scores when the culture licenses
  disagreement (De-Arteaga et al., 2020, during an actual AFST software glitch).
- **The ~30% upper bound contradicts field evidence.** In the AFST's real operation,
  screeners disagreed with the score roughly one-third of the time — and those
  overrides *improved* racial equity (screen-in disparity 20% → 9%; Cheng et al.,
  2022), coexisting with the tool's overall disparity-reducing effect (Rittenhouse et
  al., 2026). A 25–35% override rate is what functioning, value-adding discretion has
  actually looked like in child welfare. Meanwhile Green & Chen (2019a, 2019b) show
  human deviations can also be systematically biased and underperforming — so override
  *quality*, not just quantity, is the object of interest.
- **Revision adopted (§8.6):** override rate becomes a *diagnostic distribution*, not a
  two-sided target: investigate near-zero rates as probable automation bias;
  investigate sustained rates above ~40–50%, or overrides that underperform
  recommendations on later-observed outcomes, as calibration/trust failures; analyze
  override reasons as feedback on the matching criteria (Kawakami et al., 2022 — worker
  engagement depends on the tool's objective matching their own).

## 7.11 A12 — The equity evidence chain, corrected and strengthened

The framework's claim that system contact is pervasive and racially unequal now rests on
the verified chain: 37.4% of all U.S. children — 53.0% of Black children — experience a
CPS investigation by age 18 (Kim et al., 2017); cumulative California birth-cohort rates
show 26.3% investigated, 4.3% placed, 1.1% TPR, with stark racial differences
(Putnam-Hornstein et al., 2021; nationally, Edwards et al., 2021); foster-care placement
by 18 reaches 15.4% for Native American and 11.5% for Black children in the
highest-rate years (Wildeman & Emanuel, 2014). On mechanism, the framework cites both
sides of the poverty-exposure vs. residual-bias debate — Drake et al. (2011, 2023)
and Dettlaff et al. (2011, corrected here to its actual decision point: race remained a
significant predictor of *substantiation* after controlling for income and assessed
risk) — because the proxy-risk audit (Doc 05 §5.3) is warranted under either mechanism.

## 7.12 A13 — Methods check on the pilot design

The stepped-wedge choice is supported (Hemming et al., 2015 explicitly endorse it when
the intervention will roll out to all clusters; Chen, Pan & Kainz, 2021 legitimize it
for social work research). Two corrections adopted in Doc 06:

1. **The power sketch must use closed-cohort methods.** With ~7 workers per unit
   measured repeatedly across periods, the Hussey & Hughes (2007) cross-sectional model
   overstates power; the calculation now follows Hooper et al. (2016) and Hemming &
   Taljaard (2016) with within-worker autocorrelation and a decaying cluster
   autocorrelation, reported as a sensitivity range over ICC and CAC rather than a
   point estimate. The realistic minimum detectable effect shifts toward d ≈ 0.35+.
2. Reviewers will expect explicit secular-trend modeling (hiring waves, caseload
   composition shifts) — already implied by step fixed effects, now stated.

## 7.13 Method notes and verification limits

Verification was performed against publisher DOI records, agency documents, and
multiple independent secondary sources; a small number of paywalled or bot-blocked
pages (ScienceDirect, qic-wd.org, uh.edu PDF host) were verified through at least two
independent secondary records instead of the primary PDF. Two sources warrant
spot-checking before formal submission: the exact intermediate percentages in Flower et
al. (2005) (3–5-worker permanency rates are quoted with slight variation across
secondary sources), and page-level wording of QIC-WD umbrella summaries (verified via
UNL Digital Commons mirrors). All references, with DOIs/URLs, are consolidated in
[references.md](references.md).
