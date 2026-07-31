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
- Audit findings go to the oversight body (§5.6) with public summary statistics.

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
- **Kill criteria** stated in advance: sustained override rates above threshold,
  demonstrated scoring disparity uncorrected across two audit cycles, or evidence of
  performance-management misuse suspend the deployment pending remediation. A system
  whose de-commissioning conditions are unstated will not be trusted and should not be.

## 5.7 Legal and policy alignment notes

- Consistent with the operations-supporting (not rights-impacting) classification under
  OMB AI-governance guidance for public agencies (M-24-10 lineage) — verify against the
  current version and any state equivalents (e.g., state algorithmic-accountability
  statutes) at deployment.
- ICWA handling (Doc 02 §2.4) implements, and cannot substitute for, the agency's legal
  obligations; tribal partners SHOULD be consulted on the ICWA credential standard.
- Records generated (scores, overrides, audits) are agency records; retention and
  discoverability should be reviewed with counsel *before* pilot, with §5.1 rule 5
  reflected in policy.
- Where collective-bargaining agreements govern workload or assignment, the weighted
  caseload caps and the WCP MUST be reconciled with CBA terms.
