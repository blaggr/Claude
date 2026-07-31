# CASE-MATCH: Complexity-Aligned Staffing and Equitable Matching in Child Welfare

**A research-grade framework for matching child welfare case complexity to caseworker
skills, experience, and caseload — at the individual worker, supervisor/unit, and
agency levels.**

Version 0.2 (working draft; literature-reviewed) · July 2026

---

## What this is

CASE-MATCH is a measurement-and-optimization framework for one of the most consequential
and least systematized decisions in public child welfare: **which worker gets which case.**
Most agencies assign cases by rotation ("next up"), geography, or raw caseload counts.
None of those methods considers whether the worker's skills fit what the case actually
demands, whether the case's true workload weight fits the worker's remaining capacity, or
whether the resulting distribution of hard cases is equitable across a unit.

The framework has three layers:

1. **Measurement.** Two new instruments, specified from scratch so any agency can
   populate them from data it already has (SDM/CANS scores, HR and training records,
   supervisor ratings):
   - the **Case Complexity Index (CCI)** — a 7-domain, behaviorally anchored rating of
     what a case demands, yielding both a domain profile (for matching) and a scalar
     case weight in workload points (for capacity accounting);
   - the **Worker Capability Profile (WCP)** — a triangulated profile of each worker's
     skills, experience, credentials, capacity, and development goals.

2. **Algorithm.** A lexicographic, safety-first assignment and rebalancing optimizer:
   hard constraints (credentials, statutory caps, conflicts) → safety-critical skill
   floors for the most complex cases → match quality → workload equity → continuity
   (transfer minimization). Runs in three modes: online intake assignment, periodic
   rebalancing, and worker-departure redistribution. It is a **decision-support** tool:
   it recommends and explains; supervisors decide.

3. **Evaluation.** A four-phase plan — psychometric validation of both instruments, a
   retrospective-replay simulation study, a stepped-wedge cluster pilot with worker- and
   process-level primary outcomes, and a scale-up monitoring regime — designed to be
   fundable and publishable.

## What this is not

CASE-MATCH does **not** predict maltreatment risk, score families, or make any decision
about a child or family. It scores *the work a case requires* and *the capability and
capacity of the workforce*, and it recommends worker–case pairings to a human supervisor.
This distinction is central to the governance design (see
[docs/05-governance-ethics.md](docs/05-governance-ethics.md)).

## Document map

| Doc | Contents |
|---|---|
| [01-background.md](docs/01-background.md) | Problem statement, evidence base, positioning relative to predictive-risk tools, design principles |
| [02-case-complexity-index.md](docs/02-case-complexity-index.md) | CCI domains, anchors, scoring, stage multipliers, case-weight calibration, re-scoring triggers |
| [03-worker-capability-profile.md](docs/03-worker-capability-profile.md) | Skill vector, credentials, experience index, capacity model, development goals, well-being guardrails |
| [04-matching-algorithm.md](docs/04-matching-algorithm.md) | Match-quality function, lexicographic objective hierarchy, formal MILP, three operating modes, supervisor- and agency-level layers |
| [05-governance-ethics.md](docs/05-governance-ethics.md) | Human-in-the-loop rules, family- and worker-side fairness, equity audits, data governance, transparency artifacts |
| [06-evaluation-plan.md](docs/06-evaluation-plan.md) | Phase A instrument validation, Phase B simulation, Phase C stepped-wedge pilot, Phase D scale & monitoring |
| [07-literature-synthesis.md](docs/07-literature-synthesis.md) | Verified evidence review of every load-bearing assumption, with verdicts |
| [08-model-revisions.md](docs/08-model-revisions.md) | Design changes adopted from the literature review — the changelog of record |
| [references.md](docs/references.md) | Consolidated verified reference list (DOIs/URLs, gray-literature flags) |

## Core design principles

1. **Safety before efficiency.** The hierarchy is lexicographic: no amount of workload
   convenience can buy an assignment that violates a safety-critical skill floor or a
   statutory cap.
2. **Complexity earns capability.** The families with the most complex cases — who are
   disproportionately poor and disproportionately families of color — should
   systematically receive the *most* capable available workers, not whoever is next in
   rotation. Matching is an equity intervention, not just an efficiency one.
3. **Weighted caseload, not case counts.** A caseload of 15 simple in-home cases and a
   caseload of 15 complex-permanency cases are not the same job. All capacity accounting
   uses calibrated workload points.
4. **Continuity is expensive to break.** Every reassignment of an existing case carries
   an explicit penalty scaled to relationship duration and case stage, reflecting
   evidence that worker changes delay permanency.
5. **Workers develop; the model should help.** Controlled "stretch" assignments are a
   feature, not noise — bounded, supervisor-flagged, and coupled to supervision capacity.
6. **Humans decide, and overrides are data.** Every recommendation is explainable;
   every override carries a reason code that feeds monitoring and model improvement.
7. **Measure the workforce with the same rigor as the work.** Instruments on both sides
   of the match get real psychometrics: reliability targets, validity evidence, drift
   monitoring, and recalibration schedules.

## Status and intended use

This is a design-and-evaluation framework, not deployed software. Version 0.2
incorporates a structured literature review (July 2026) in which every load-bearing
assumption was checked against verified sources: the evidence review is in
[docs/07-literature-synthesis.md](docs/07-literature-synthesis.md), the resulting
design changes in [docs/08-model-revisions.md](docs/08-model-revisions.md), and the
consolidated verified reference list in [docs/references.md](docs/references.md).
Notable revisions: the transfer penalty re-specified as diminishing-marginal and
explicitly non-causal in its calibration; a new severe-case-share cap per worker;
strain-gated stretch assignments; override monitoring as a diagnostic rather than a
target; the workload rationale routed through burnout rather than raw counts; and the
policy-alignment section rewritten for the 2026 federal landscape (OMB M-25-21; ACF's
2026 predictive-analytics guidance). The intended next steps are (a) SME panel review
of the CCI and WCP item sets, and (b) the Phase B simulation study using retrospective
administrative data from a partner agency.
