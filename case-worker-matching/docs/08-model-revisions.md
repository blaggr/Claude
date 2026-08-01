# 8. Model Revisions Adopted from the Literature Review

This section records the design changes made in response to the evidence review in
[07-literature-synthesis.md](07-literature-synthesis.md) — what changed, why, and where.
Each revision has been applied to the framework documents (Docs 01–06); this file is
the changelog and rationale of record.

## 8.1 Positioning and novelty (Doc 01)

**Change.** The claim that worker–case assignment is "the last unsystematized decision"
is narrowed. The framework now cites Baron et al. (2024) — mechanism-design reassignment
of CPS investigators — and adjacent allocation work (Kube et al., 2019; Highsmith,
2024; state staff-allocation tools), and claims specifically: *no prior prospectively
evaluated system matching measured case complexity to measured worker capability and
capacity under safety-floor, weighted-caseload, equity, and continuity constraints.*
The distinction from Baron et al. is substantive, not just chronological: theirs
optimizes against predicted case outcomes; CASE-MATCH is a measurement-first approach
that never predicts family outcomes — which is also what keeps it outside the
family-scoring governance regime.

**Change.** The nursing analogue is downgraded from "evidence-backed" to "structurally
established, empirically unproven at the assignment level" (Griffiths et al., 2020),
with the trial gap stated as part of the framework's motivation. The framework
additionally anchors itself in the algorithmic work-allocation literature (Lee et al.,
2015; Uhde et al., 2020; Ammitzbøll Flügge et al., 2021; Moon & Guha, 2026).

## 8.2 Transfer penalty re-specified (Doc 04 §4.3/§4.5)

**Change.** The penalty form `τ_i = τ₀ · dur(i)^γ · stage_i` is replaced by a
**diminishing-marginal-transfer form**: for case `i` with prior transfer count `k_i`,

```
τ_i(k_i) = τ₀ · φ^{k_i} · g(dur_i) · stage_i        with φ < 1 (default 0.6)
```

so the *first* transfer of a long-standing relationship costs the most and each further
transfer adds less marginal penalty — matching the relationship-disruption mechanism
(Hoffmeister, 2026; Ahn et al., 2025; Strolin-Goltzman et al., 2010) rather than the
confounded permanency-cliff percentages (Flower et al., 2005). `g(dur)` remains concave
in relationship duration; milestone lockouts are unchanged.

**Change.** τ₀, φ are documented as **policy parameters with mandatory sensitivity
analysis in Phase B** — explicitly *not* empirical estimates. Any future data-driven
calibration must condition on case complexity and duration (Kothari et al., 2021 shows
severity drives both transfers and departures) or transfers will be blamed for harm
that case difficulty caused.

**Change.** Doc 01's evidence summary now characterizes the continuity evidence
honestly: robust observational association + mechanism evidence; gray-literature caveat
on Flower et al.; MacLochlainn et al. (2026) cited as the current synthesis.

## 8.3 CCI anti-gaming moves into operating procedure (Doc 02)

**Change.** The "known measurement risks" section is upgraded from mitigations-noted to
mechanisms-specified, on the strength of Campbell (1979), Silverman & Skinner (2004),
Bosk (2018), and Fasoli & Haddock (2010):

1. **Standing blind double-rating audit**: each quarter, a random ~5% sample of active
   cases is independently re-rated by a rater outside the unit (the Junttila et al.,
   2023 model from nursing acuity systems); audit-vs-operational score drift is a
   standing report to the steering body.
2. **Drift triangulation**: score distributions monitored by office and rater against
   time-study re-checks; upward drift in scores without corresponding drift in logged
   hours is the upcoding signature.
3. **Crosswalk narrowed**: SDM pre-population uses the actuarial *risk* scales only
   (Baird & Wagner, 2000; Johnson, 2011); the SDM safety assessment is not used as a
   validity anchor (McNellan et al., 2022).
4. **INTERMED cited as design precedent** (Huyse et al., 1999; de Jonge et al., 2005),
   and the CCI's validation plan mirrors its sequence (anchored multi-domain rating →
   interrater reliability → criterion validity against effort).

## 8.4 WCP: BARS repositioned; reliability burden shifts to process (Doc 03)

**Change.** The WCP no longer claims BARS anchors *produce* reliability (the evidence
says format contributes little — Schwab et al., 1975; Landy & Farr, 1980). Anchors are
retained for transparency, contestability, and rater acceptance (Jacobs et al., 1980);
the reliability investment is re-specified as: mandatory rater training, semi-annual
calibration sessions across supervisors, and the Phase A dual-rating study with the
live disagreement stream. Worker-facing legitimacy (Doc 05 §5.4) is now an explicit
design goal of the anchor text, consistent with its actual evidentiary strengths.

## 8.5 New constraint: severe-case share cap; strain-gated stretch (Docs 03–04)

**Change (new L0 constraint).** Motivated by Hensel et al. (2015 — caseload *ratio* of
trauma cases predicts secondary traumatic stress more strongly than volume; bridged to
child welfare by Sprang et al., 2011 and Barbee et al., 2023):

```
Σ_i [T(i) ∈ {T3, T4}] · x_ij  ≤  ρ_max · Σ_i x_ij     ∀j     (default ρ_max = 0.4)
```

— no worker's caseload may exceed a policy share of high-tier cases, regardless of
total weighted utilization. This closes a real gap: L3 balances total load but would
otherwise happily concentrate every severe case on one under-utilized expert. The
scarce-expertise reservation (Doc 03 §3.6) and this cap jointly bound the "competence
tax" from both sides.

**Change.** The stretch gates gain a fourth condition (Courtright et al., 2014: high
challenge with low self-efficacy/support produces exhaustion): stretch bonuses are
**suppressed while a worker's strain indicators are elevated** (sustainability
adjustment active, post-critical-incident window, or utilization > 92% in the prior
period). DeRue & Wellman (2009) is cited for why the supervision-capacity gate is the
mechanism, not bureaucracy.

**Change.** The new-worker ramp is re-labeled "documented practice consistent with
onboarding science" (Alaska OCS; NYC ACS; CWIG, 2022; QIC-WD onboarding findings), not
evidence-based per se.

## 8.6 Override monitoring re-specified (Docs 04 §4.7, 05 §5.6)

**Change.** The two-sided override-rate target (near-0% / >30%) is replaced by a
**diagnostic-distribution regime**:

- near-zero override rates trigger an automation-bias review (Skitka et al., 1999; the
  De-Arteaga et al., 2020 evidence that catching errors requires a culture that
  licenses disagreement);
- sustained rates above ~40–50%, *or overrides that underperform recommendations on
  subsequently observed match outcomes*, trigger calibration/trust review (Green &
  Chen, 2019a, 2019b);
- the reference point that functioning discretion in child welfare has looked like
  ~25–35% disagreement — and improved equity when it did (Cheng et al., 2022;
  Rittenhouse et al., 2026) — is stated so that no manager treats overrides as failure;
- override *reasons* are analyzed as feedback on the matching criteria themselves
  (Kawakami et al., 2022), reviewed at each calibration cycle.

## 8.7 Workload rationale restated (Docs 01–02)

**Change.** The causal chain is restated: weighted workload manages the demands side of
a demands–resources system (He et al., 2018) whose effects on retention run through
perceived workload and burnout (Paul, 2021; Lushin et al., 2023) — with Kim & Kao
(2014) cited as the explicit counterweight showing objective caseload counts alone do
not predict turnover intention. This is presented as the argument *for* weighted
workload: the weight is a better proxy for the perceived-demand construct that actually
predicts outcomes. CWLA figures are corrected (12 investigations/month; 15–17 in-home
families; 12–15 foster care) and presented as historical benchmarks with CWLA's own
"a number is not sufficient" caveat; SB 2030 attribution corrected (AHA & WRMA jointly,
for CDSS, 2000).

**Change (evaluation).** Retention and STS/well-being are registered as *distinct*
outcome families in Phase C (the QIC-WD Resilience Alliance null — coping improved,
turnover unchanged — plus the positive selection and organizational-climate findings),
so the pilot does not assume well-being gains convert to retention.

## 8.8 Governance section rewritten for the 2026 landscape (Doc 05 §5.7)

**Change.** M-24-10 references are replaced: the operative federal guidance is
**OMB M-25-21** (April 3, 2025), whose single "high-impact AI" category replaces the
rights/safety-impacting taxonomy. The framework performs the classification analysis
explicitly: (i) toward families, CASE-MATCH's output is not a principal basis for any
decision with legal or material effect on them — the design rules in §5.1–5.2
guarantee this; (ii) toward *workers*, assignment can be a significant employment
effect, so the framework voluntarily adopts M-25-21's minimum practices (impact
assessment, pre-deployment testing, ongoing monitoring, human oversight, training) and
flags the state-law employment prongs (Colorado's successor ADMT framework effective
2027; California AB 302 inventory; CPPA ADMT rules binding vendors). ICWA, CBA, and
records-retention obligations are unchanged.

**Change.** The federal-posture framing is updated: ACF's 2026 guidance actively
encourages predictive analytics under human-in-the-loop, workforce, and transparency
conditions (ACF/ACYF 2026 issue brief; IM-26-03; June 2026 pilot funding). CASE-MATCH
is positioned as complementary workforce-side infrastructure that builds exactly the
capacity those conditions require, while maintaining its bright line: it never scores
families, and the AFST civil-rights record (AP 2022–2023; Gerchick et al., 2023;
balanced by Rittenhouse et al., 2026) is cited as the reason that line exists.

**Change.** Moon & Guha (2026) is added to §5.3's audit rationale: allocation
algorithms under scarcity can concentrate disadvantage, so the equity audit explicitly
monitors *which families and which workers systematically receive the lowest-scoring
feasible matches* ("leftover" matches), not only average parity.

## 8.9 Evaluation plan corrections (Doc 06)

1. Content validity criterion: **I-CVI ≥ .78, S-CVI/Ave ≥ .90** (computation method
   specified) per Polit & Beck (2006, 2007), replacing CVI ≥ .80.
2. Power analysis: closed-cohort stepped-wedge methods (Hooper et al., 2016; Hemming &
   Taljaard, 2016) with within-worker autocorrelation and decaying cluster
   autocorrelation, reported as an MDES sensitivity range over ICC and CAC (realistic
   MDES ≈ 0.30–0.40, not a 0.30–0.35 point claim); Hussey & Hughes (2007) retained for
   the design's canonical statement.
3. ICC/kappa targets keep their citations (Cicchetti, 1994; Koo & Li, 2016; Landis &
   Koch, 1977) with the caveat that all such benchmarks are conventions.
4. Phase A adds the standing blind double-rating audit (§8.3) as a permanent
   post-validation reliability mechanism, not a one-time study.
5. Phase B sensitivity analysis now explicitly includes τ₀, φ (transfer penalty) and
   ρ_max (severe-share cap).
6. Outcome hierarchy: retention/turnover and STS/burnout registered as distinct
   families (§8.7).

## 8.10 What did not change, and why

- **The lexicographic hierarchy** (safety floors before match quality before equity
  before continuity) — nothing in the review contradicts it, and the nursing
  safety-floor logic survives as structural precedent even with the effectiveness
  caveat.
- **Decision-support posture** — strengthened, if anything: the field evidence that
  human discretion adds equity value on top of algorithmic recommendations (Cheng et
  al., 2022; Rittenhouse et al., 2026) is the empirical case for exactly this design.
- **Weighted caseload accounting** — the review found this the framework's
  best-supported commitment (§7.4).
- **The dual-rating CCI procedure and live IRR stream** — now additionally justified as
  the anti-drift mechanism the acuity literature says is mandatory.
