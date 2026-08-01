# 5. Governance, Ethics, and Fairness

CASE-MATCH scores work and workforce, not families — but it still reallocates
professional attention across families and shapes the working lives of staff. Both edges
need governance. This section specifies binding rules (MUST), defaults (SHOULD), and the
audit regime that makes them checkable.

## 5.1 Human-in-the-loop rules (binding)

1. The system MUST NOT execute any assignment or transfer without an authorized human
   decision. All modes are recommend-and-explain.
2. Every recommendation MUST display its component scores, binding constraints, and
   near-miss exclusions — no bare rankings.
3. Supervisors MUST be able to select any feasible worker without friction beyond a
   reason code; infeasible requests route as exceptions, never as silent denials.
4. Escalations (`q_i = 1`) MUST reach a human owner within a policy-defined SLA; an
   escalation queue nobody owns is a system failure.
5. No output of the system may be used as evidence in any proceeding concerning a family.

## 5.2 What the system must never do

- Predict maltreatment, score family risk, or influence screening, removal,
  reunification, or TPR decisions. (The CCI ingests *existing* assessments as workload
  inputs; it produces no family-facing judgment.)
- Auto-assign or auto-transfer, in any configuration, in this version.
- Rank or grade workers publicly, or feed dashboards that function as league tables.
- Use well-being/sustainability data (Doc 03 §3.5) for evaluation, discipline, or
  promotion — see §5.4.

## 5.3 Family-side equity

The central equity claim of the framework is directional: because complexity earns
capability (Doc 01 §1.6), families with the heaviest, most systems-entangled cases —
disproportionately poor families and families of color — systematically receive more
skilled workers with more protected capacity than rotation gives them. That claim must
be *demonstrated, not assumed*:

- **Scoring-disparity audit** (semi-annual): distribution of CCI domain scores and tiers
  by race/ethnicity, language, and geography, conditioned on case characteristics —
  looking for domains functioning as demographic proxies beyond their workload meaning.
  Poverty-linked domains (D3, D5) are expected to correlate with demography; the audit
  asks whether *equal circumstances score equally*.
- **Match-quality parity audit**: realized `M(i,j)` and time-to-assignment by family
  demographics. The directional claim predicts parity or advantage for high-complexity
  groups; a deficit is a red flag that overrides or configuration are leaking bias.
- **Continuity parity**: transfer rates (`z`) by demographics — reassignment churn must
  not concentrate on any group.
- **"Leftover match" monitoring**: allocation algorithms under scarcity can concentrate
  disadvantage even without scoring anyone (Moon & Guha, 2026). The audit therefore
  tracks not only average parity but *which families and which workers systematically
  receive the lowest-scoring feasible matches* — the tail of the match-quality
  distribution, by demographics and by unit.
- Audit findings go to the oversight body (§5.6) with public summary statistics.

The prevalence backdrop that makes this auditing non-optional: 37.4% of all U.S.
children — and 53.0% of Black children — experience a CPS investigation by age 18 (Kim
et al., 2017); cumulative placement and TPR rates show equally stark disparities
(Putnam-Hornstein et al., 2021; Edwards et al., 2021; Wildeman & Emanuel, 2014). The
framework cites both the differential-exposure and residual-bias accounts of these
disparities (Drake et al., 2011, 2023; Dettlaff et al., 2011 — race predicted
*substantiation* net of income and risk) because the proxy-risk audit is warranted
under either mechanism.

## 5.4 Worker-side fairness

Workers are the measured subjects of the WCP; they get data-subject protections:

- **Full transparency**: every worker can see their complete profile, every capacity
  adjustment, and the anchors behind every rating. No hidden fields.
- **Contest and calibration**: a worker who disputes a rating gets a calibration
  conference (worker, supervisor, one uninvolved rater) with a written outcome. Dispute
  rates per supervisor are themselves monitored.
- **Firewall on sustainability data**: well-being inputs enter only as reason-free
  capacity adjustments; raw instrument responses are never stored in the operational
  system, never visible to management chains, never carried into personnel files.
  Agencies that cannot guarantee the firewall MUST run without instrumented well-being
  input.
- **No performance-management use**: WCP skill scores and utilization figures are
  assignment inputs, not appraisal evidence. The document trail (this section) is the
  commitment labor partners will ask for; where staff are represented, the WCP design
  and this use-limitation SHOULD be negotiated before pilot, not after grievance.
- **Anti-exploitation checks**: monitoring for the "competence tax" pattern — the same
  workers persistently at high utilization with high T4 share. L3 exists to prevent it;
  the audit verifies L3 is not being overridden away.

## 5.5 Transparency artifacts

The deployment MUST publish, internally at minimum:

1. **Model card**: purpose, inputs, weights and guardrails, levels and tolerances (ε,
   headroom), what the system cannot do, known limitations, audit schedule.
2. **Plain-language staff guide**: how scores are made, how to read a recommendation,
   how to override, how to contest a profile.
3. **Family-facing statement** (agency SHOULD): a public description that the agency
   uses a workload-equity tool to match staffing to family needs, in plain language.
   Families are affected parties even though they are not scored subjects.
4. **Configuration change log**: every weight, floor, cap, or tolerance change, with
   who/when/why — configuration is where governance erodes quietly.

## 5.6 Oversight and accountability structure

- **Steering body** with worker representation (including union where present),
  supervisor representation, agency leadership, and at least one external member (family
  representative or community advocate). Owns configuration approval, audit review, and
  the surge-posture switch (Doc 04 §4.9).
- **Drift and health monitoring** (operational, monthly): override rates by unit and
  reason; escalation counts; utilization dispersion; stale-profile counts; scoring drift
  vs. time-study re-checks.
- **Kill criteria** stated in advance: override patterns in the calibration-failure
  range of the diagnostic regime (Doc 04 §4.7) uncorrected across two cycles,
  demonstrated scoring disparity uncorrected across two audit cycles, or evidence of
  performance-management misuse suspend the deployment pending remediation. A system
  whose de-commissioning conditions are unstated will not be trusted and should not be.

## 5.7 Legal and policy alignment (updated July 2026)

**Federal AI governance.** OMB M-24-10 (March 2024) was rescinded on April 3, 2025 and
replaced by **M-25-21** (use and governance) and M-25-22 (procurement) under E.O.
14179; M-25-21 is the operative guidance as of this writing. Its single **"high-impact
AI"** category — AI whose output is "a principal basis for decisions or actions with
legal, material, binding, or significant effect" — replaces the earlier
rights-impacting/safety-impacting taxonomy. The framework performs that classification
explicitly rather than asserting exemption:

- *Toward families*: CASE-MATCH's output is not a principal basis for any decision
  with legal or material effect on a family — the binding rules in §5.1–5.2 are what
  guarantee that, and weakening them would change the classification, not just the
  ethics.
- *Toward workers*: assignment materially shapes working conditions, and employment
  decisions appear in the "significant decision" prongs of state frameworks. The
  deployment therefore **voluntarily adopts M-25-21's minimum practices** — AI impact
  assessment, pre-deployment testing, ongoing monitoring, human oversight, and staff
  training — as its floor, whatever the formal classification.

**Federal child welfare posture.** ACF now actively encourages predictive analytics in
child welfare under human-in-the-loop, workforce-capacity, and transparency conditions
(ACF/ACYF issue brief on predictive risk modeling, March 2026; ACYF-CB-IM-26-03 on
CCWIS modernization; state pilot funding announced June 2026). CASE-MATCH aligns as
*complementary workforce-side infrastructure* — it builds the workforce capacity those
conditions presuppose — while maintaining its bright line against family scoring, for
which the AFST civil-rights record (AP investigations 2022–2023, DOJ Civil Rights
Division interest; Gerchick et al., 2023; balanced by Rittenhouse et al., 2026) is the
standing reason.

**State law (a moving target — re-verify at deployment).** As of July 2026: Colorado's
AI Act is nominally effective but enforcement-suspended and slated for replacement by a
narrower ADMT framework effective January 2027; California's relevant instruments are
AB 302 (state agencies must inventory high-risk automated decision systems — expect a
deployed CASE-MATCH to be listed) and the CPPA ADMT regulations (binding vendors;
employment "significant decision" compliance from January 2027). Any deployment should
brief counsel on the then-current versions.

**Unchanged obligations.**
- ICWA handling (Doc 02 §2.4) implements, and cannot substitute for, the agency's legal
  obligations; tribal partners SHOULD be consulted on the ICWA credential standard.
- Records generated (scores, overrides, audits) are agency records; retention and
  discoverability should be reviewed with counsel *before* pilot, with §5.1 rule 5
  reflected in policy.
- Where collective-bargaining agreements govern workload or assignment, the weighted
  caseload caps and the WCP MUST be reconciled with CBA terms.
