# 4. The Matching Algorithm

This section specifies the optimization layer: the match-quality function, the
lexicographic objective hierarchy, the formal program, the three operating modes
(online intake, periodic rebalancing, departure redistribution), and the supervisor- and
agency-level layers built on top of the individual-level engine.

Notation: cases `i ∈ I` (new arrivals `B`, existing `E`), workers `j ∈ J` grouped into
units `u(j)`, CCI domain profile `c_i = (c_{i1}…c_{i7})`, tier `T(i)`, weight `w_i`,
requirements `R(i)`, supervision intensity `σ_i`; worker skill vector `s_j`, credentials
`Q_j`, experience tier `E(j)`, capacity `κ_j`, raw cap `K_j`; assignment variables
`x_{ij} ∈ {0,1}`; for existing cases, incumbent worker `a(i)` and transfer indicator
`z_i = 1 − x_{i,a(i)}`.

## 4.1 Overview of the hierarchy

```
L0  Feasibility (hard):   credentials & exclusions · weighted cap κ · raw cap K ·
                          supervision budget S_u · leave/eligibility
L1  Safety floors (hard, with escalation slack):
                          every T4 (and flagged T3) case reaches a worker meeting
                          per-domain skill floors on its critical domains
L2  Match quality:        maximize Σ M(i,j)·x_ij
L3  Workload equity:      minimize utilization dispersion, within tolerance ε of L2
L4  Continuity:           minimize transfer cost Σ τ_i z_i (rebalancing modes),
                          within tolerance of L3
```

Lexicographic means literally sequential: the solver optimizes L2 only over assignments
that satisfy L0–L1; L3 only over solutions within `(1−ε)` of the L2 optimum; and so on.
This is implemented either as sequential solves with optimum-value constraints or as a
single weighted objective with order-of-magnitude separated weights; the sequential form
is preferred because each level's attained value is separately reportable — an
auditability property, not just a solver convenience.

## 4.2 Match-quality function `M(i,j)`

`M(i,j) ∈ [0,100]`, a weighted sum of five interpretable components. Every recommendation
displays the components, not just the total.

**(a) Skill–need alignment (weight ~50).** For each domain `d`, compare need `c_{id}`
with skill `s_{jd}` using an **asymmetric gap function**:

```
fit_d(i,j) = 1                          if s_jd ≥ c_id            (met)
           = 1 − β·(c_id − s_jd)        if s_jd < c_id            (shortfall, β ≈ 0.45)
overqual(i,j) = δ · Σ_d max(0, s_jd − c_id − 1)                   (surplus, δ ≈ 0.03)
A(i,j) = Σ_d ω_id · fit_d(i,j) / Σ_d ω_id  −  overqual(i,j)
```

where `ω_id = c_id` (a case's own needs weight its own match — a domain the case doesn't
need can't drive its match score). Shortfall is penalized roughly an order of magnitude
more than surplus: the surplus discount exists only to keep scarce experts from being
absorbed by routine cases, never to punish competence. β is set so that a 2-point
shortfall on a heavily weighted domain is nearly disqualifying in ranking terms even
when L1 doesn't formally bind.

**(b) Experience-tier congruence (weight ~15).** A lookup matrix on `(T(i), E(j))`:
full credit on or above the diagonal, graded penalty below it, consistent with the
eligibility rules in Doc 03 §3.3.

**(c) Continuity (weight ~15).** Credit for prior productive relationship with this
family or a sibling's case, scaled by relationship duration and recency; zero for new
families. (Distinct from the L4 transfer penalty, which protects *existing* assignments;
this component *seeks* reunions at new assignment.)

**(d) Logistics (weight ~10).** Travel-time burden between worker's base/territory and
the family/placements; language convenience above credential minimums.

**(e) Developmental stretch (weight ~10, gated).** Bonus if the case exercises a flagged
growth domain `g_j`, subject to the three gates in Doc 03 §3.5 (tier ≤ demonstrated+1,
supervisor flag, supervision budget). Ungated stretch would let the optimizer discover
that "development" is a cheap way to dump hard cases on juniors; the gates make it a
supervised apprenticeship mechanism.

Component weights are agency-configurable within guardrails (alignment may not fall
below 40; stretch may not exceed 15) and are part of the transparency artifact set
(Doc 05 §5.5).

## 4.3 Formal program (rebalancing mode; other modes are restrictions)

```
Sets/params as above.  Variables: x_ij ∈ {0,1};  q_i ∈ {0,1} escalation slack;
z_i = 1 − x_{i,a(i)} for i ∈ E.

(1) Σ_j x_ij + q_i = 1                       ∀i           each case assigned or escalated
(2) x_ij = 0                                 ∀(i,j): Q_j ⊉ R(i), or exclusion, or
                                             j ineligible (leave, tier rule w/o stretch)
(3) Σ_i w_i x_ij ≤ κ_j                       ∀j           weighted capacity
(4) Σ_i x_ij ≤ K_j                           ∀j           raw statutory cap
(5) Σ_i σ_i x_ij summed over j∈u ≤ S_u       ∀u           supervision budget
(6) x_ij = 0   ∀ i: T(i)=T4, j: s_jd < f_d(i) on any critical domain d of i
                                                          safety floor (critical domains:
                                                          those with c_id = 3; floors f_d
                                                          set by policy, default s ≥ 2)
L1: minimize Σ_{i: T4∨flagged} q_i           (escalations; ideally 0)
L2: maximize Σ_ij M(i,j) x_ij                subject to L1 optimum
L3: minimize η  s.t.  ū−η ≤ u_j ≤ ū+η ∀j,    u_j = Σ_i w_i x_ij / κ_j,
    subject to Σ M x ≥ (1−ε)·L2* (default ε = 0.03)
L4: minimize Σ_{i∈E} τ_i z_i                 subject to L3 within tolerance
```

**Escalation is a feature.** `q_i = 1` means *no eligible worker in scope can safely
carry this case* — the model must say so loudly rather than silently degrade the match.
Escalated cases route up: unit → office → agency queue (§4.8), and persistent
escalations are the agency's capability-gap signal (§4.9).

**Transfer penalty.** `τ_i = τ₀ · dur(i)^γ · stage_i`, increasing in relationship
duration (concave, γ≈0.5) and stage-scaled, with **milestone lockouts**: `z_i` is fixed
to 0 (transfer prohibited) within a policy window of a TPR hearing, permanency
milestone, or imminent reunification, absent supervisor-initiated cause.

**Tractability.** Without side constraints this is an assignment/min-cost-flow problem;
with them it is a small MILP. Realistic instances (unit: 5–8 workers × dozens of cases;
office: ~10² workers × 10³ cases) solve in seconds with any modern solver (CBC/HiGHS
suffice; no commercial dependency needed). Lexicographic levels multiply solve count by
four, which is immaterial at this scale.

## 4.4 Mode 1 — Online intake assignment (daily / per-arrival)

New cases arrive continuously; decisions cannot wait for a batch. Protocol:

1. **Micro-batching**: accumulate arrivals over the agency's natural cycle (e.g.,
   morning court/intake run and afternoon run); assign each batch by solving the program
   with `E` fixed (`z ≡ 0`), i.e., only new cases move.
2. **Immediate-need path**: cases requiring same-hour assignment (investigation
   response) use the greedy rule: assign to the feasible worker maximizing
   `M(i,j) − λ·(u_j after assignment − ū)` — match quality with a marginal-congestion
   regularizer, λ calibrated in simulation (Doc 06 §B) so greedy stays near batch-optimal.
3. **Capacity headroom rule**: the online mode never fills a worker past a headroom
   threshold (default 92% utilization) except by supervisor override, preserving slack
   for the unpredictable arrivals that define this work.

## 4.5 Mode 2 — Periodic rebalancing (monthly/quarterly)

Full program of §4.3 with transfers allowed. In practice the recommendation set is
constrained to be **small and legible**: a maximum of `k` proposed transfers per unit
per cycle (default 3), presented as a diff — "move case X from worker A (utilization
118%, D4 shortfall) to worker B (utilization 74%, D4 = 3), transfer cost: moderate
(14-month relationship)". Rebalancing recommendations are *always* decision-support;
no transfer executes without the supervisor of both sending and receiving workers.

## 4.6 Mode 3 — Departure redistribution

A resignation or extended leave orphans an entire caseload at once — the most common
real-world bulk reassignment and the moment current practice is worst (cases scatter to
whoever has count-room). Protocol: solve the rebalancing program with the departing
worker's cases forced to move (`x_{i,j⁻} = 0`), *allowing* a bounded ripple (up to `k`
secondary transfers) so that the departing worker's T4 cases can displace T1 cases from
the best-matched receivers rather than defaulting to whoever has raw capacity. The
ripple bound keeps the disruption legible; the default no-ripple solution is also shown
for comparison.

## 4.7 Decision-support presentation and overrides

For each case, the supervisor sees the **top 3 feasible workers** with: total `M`,
the five components, resulting utilization for each candidate, any stretch flags, and
any near-miss constraints ("worker C excluded: ICWA credential expired 3/2026").
Supervisors may:

- accept a recommendation;
- choose any other *feasible* worker (recorded as soft override, reason code);
- request an infeasible assignment → routed as an exception request one level up
  (hard override; reason code; time-limited if it breaches a cap).

Reason codes (worker circumstances, family-specific history, team development, other +
free text) feed drift monitoring and calibration review (Doc 06 §D). Override *rate* is
a health metric with a two-sided target: near-0% suggests rubber-stamping, above ~30%
suggests the model has lost the room.

## 4.8 The supervisor/unit level

The unit engine is the same program restricted to `j ∈ u`, but the supervisor layer
adds standing analytics:

- **Skill-coverage matrix**: unit's aggregate skill supply per domain vs. the unit
  caseload's aggregate demand — the at-a-glance answer to "can my unit absorb what my
  intake stream sends me?";
- **Utilization board**: `u_j` per worker with adjustment ledger visible, flagging
  anyone > 100% or persistently > 92%;
- **Supervision budget** tracking (`Σσ` vs `S_u`), which is also the formal coupling to
  supervisor capacity — a unit's ability to take complex work depends on its
  supervisor's coaching bandwidth, not just its workers' κ;
- **Stretch portfolio**: which workers are on stretch assignments in which domains —
  the unit's development plan expressed in live cases.

Cross-unit routing: when a unit cannot feasibly take an arriving case (L0/L1
infeasible or headroom exhausted), the case routes to the office-level pool and the
program re-runs over eligible units, with a geography/program-fit term added to `M`.
*Extension (out of scope v0.1):* supervisor–worker matching — the same architecture
applies one level up, treating supervision need (novice density, stretch load) as the
"case" side.

## 4.9 The agency level

The agency layer consumes the optimizer's artifacts rather than adding new machinery:

- **Capability-gap pricing.** The dual values (shadow prices) of the L1 floor and
  credential constraints — or, for the integer program, the escalation counts `Σq` and
  the match-quality loss attributable to each binding floor — literally price what the
  agency would gain by training one more worker to level `f` in domain `d` or certifying
  one more ICWA-qualified worker in office X. This turns the training budget from a
  compliance exercise into a priced portfolio decision, and it is the framework's most
  direct research-to-operations payoff.
- **Hiring-profile guidance.** Persistent escalations and floor-shortfalls by domain ×
  office define the specialist profile the next requisition should seek.
- **Equity dashboards**: distribution of utilization and of T3/T4 share across units and
  offices (are some offices systematically the dumping ground?); family-side match
  quality parity (Doc 05 §5.3).
- **Surge posture.** In declared surge (mass vacancy, disaster), the agency may relax ε
  and headroom globally rather than let violations accumulate invisibly — an explicit,
  logged, time-limited posture change, reported to leadership as such.

## 4.10 Reference implementation sketch

A reference implementation is straightforward and deliberately boring: Python +
`pandas` for the ledgers, `HiGHS`/`CBC` via `PuLP` or `python-mip` for the MILP,
sequential lexicographic solves, JSON explanation objects per recommendation. It is
specified here but not built in this version (the deliverable is the framework); the
simulation study (Doc 06 §B) will require building it and doubles as its shakedown.
