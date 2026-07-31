# 3. The Worker Capability Profile (WCP)

The WCP is the workforce side of the match: a structured, triangulated profile of each
caseworker's **skills, credentials, experience, capacity, development goals, and
sustainability guardrails**. It is designed to be populated from records agencies
already keep (HR, training/LMS, case history) plus one structured supervisor rating,
and to be fully transparent to the worker it describes (Doc 05 §5.4).

## 3.1 Components at a glance

| Component | Symbol | Feeds | Update cadence |
|---|---|---|---|
| Skill vector (7 domains, mirrors CCI) | `s_j` | Match quality (L2), skill floors (L1) | Semi-annual + post-training |
| Credential set | `Q_j` | Hard constraints (L0) | Event-driven |
| Experience index | `e_j` | Tier eligibility, match quality | Quarterly (computed) |
| Capacity (workload points) | `κ_j` | Capacity constraints (L0), equity (L3) | Monthly + event-driven |
| Development goals | `g_j` | Stretch term in match quality | Supervision cycle |
| Sustainability guardrails | — | Temporary capacity adjustment | Worker-initiated / periodic |

## 3.2 Skill vector `s_j`

Seven domains, deliberately **the same seven as the CCI** so that need and skill are
commensurable: safety practice (D1), child-needs practice (D2), family-systems practice
(D3), legal/procedural practice (D4), service coordination (D5), engagement/relational
practice (D6), and organizational tempo management (D7).

Each domain is scored 0–3 using **behaviorally anchored rating scales (BARS)** — e.g.,
D1 level 3: "has independently managed cases involving coercive-control dynamics or
threats to staff; models safety-organized practice for peers" — via triangulation:

1. **Supervisor BARS rating** (primary; anchors force behavioral evidence, and Phase A
   tests their reliability);
2. **Training and certification records** (LMS completions map to domain minimums —
   completing advanced safety-organized-practice training supports but does not by
   itself establish D1 ≥ 2);
3. **Case-history-derived experience counts** (number of ICWA cases carried, TPR cases
   to disposition, medically fragile children served — computed from SACWIS/CCWIS);
4. **Worker self-assessment** (recorded and compared, used for development conversations
   and for flagging supervisor–self gaps ≥ 2; not averaged into the operational score).

Discrepancy rule: where sources conflict, the supervisor rating governs operationally,
but persistent gaps are surfaced in the calibration review (Doc 06 §D).

## 3.3 Credentials `Q_j` and experience index `e_j`

- **Credentials** are binary and evidence-backed: ICWA-qualified, language proficiencies
  (with proficiency level), CSEC-trained, medical case management, forensic-interview
  trained, etc. They exist to satisfy `R(i)` requirements (Doc 02 §2.4). Expiration
  dates are tracked; an expired credential fails L0.
- **Experience index** `e_j` combines: total child-welfare tenure, tenure in current
  program/stage, and breadth (count of distinct case types carried to milestone).
  It maps to an **experience tier** E1–E4 used in tier-eligibility rules:
  - E1 (< 1 yr in function) — eligible for T1–T2 cases; T3 only with stretch flag.
  - E2 (1–3 yrs) — T1–T3; T4 only with stretch flag and co-assignment.
  - E3 (3–6 yrs or demonstrated mastery) — all tiers.
  - E4 (senior/specialist) — all tiers; counted as scarce capacity (§3.6).

Tiers are floors of *eligibility*, not sufficiency — L1 skill floors still apply
domain-by-domain (Doc 04 §4.3).

## 3.4 Capacity model `κ_j`

All capacity is denominated in workload points (WLP; Doc 02 §2.5), normalized so a
full-time ongoing-services worker with no adjustments has `κ = 100` per month.

```
κ_j = 100 × FTE_j × ρ_role,j − A_j
```

- `FTE_j`: contracted fraction.
- `ρ_role,j`: role factor — e.g., investigation workers on rotation intake weeks,
  workers with court-officer duties.
- `A_j`: itemized adjustments, each visible in the ledger:
  - **new-worker ramp**: −50% months 0–3, −25% months 4–6 (agency-configurable);
  - **secondary duties**: field-training/mentoring (each mentee −10), committee or
    on-call assignments (per policy schedule);
  - **planned leave** and return-from-leave ramp;
  - **post-critical-incident adjustment**: after a fatality/near-fatality on a worker's
    caseload, a temporary reduction plus a freeze on new T4 assignments — standard
    practice made systematic;
  - **sustainability adjustment** (§3.5).

Two caps coexist in the optimizer: the **weighted cap** (`Σ w_i ≤ κ_j`) and a **raw
count cap** (`Σ x_ij ≤ K_j`) reflecting statute or policy (e.g., a jurisdictional
maximum of N children per worker). Both are L0-hard.

## 3.5 Development goals and sustainability guardrails

**Development goals `g_j`.** Each supervision cycle, worker and supervisor may flag 1–2
domains as growth targets. A case that exercises a flagged domain earns a bounded
**stretch bonus** in the match score — but only when (a) the case's tier is at most one
above the worker's demonstrated tier, (b) the supervisor's stretch flag is on, and
(c) the unit's supervision-capacity constraint (§3.6) has room. Stretch is how the model
grows the workforce instead of freezing it: without it, optimization converges to
"experts get everything hard forever," which is both a burnout engine and a pipeline
failure.

**Sustainability guardrails.** Optionally, agencies may incorporate periodic well-being
screening (e.g., ProQOL burnout/STS subscales) as a *worker-initiated or confidential*
input that temporarily lowers effective capacity or pauses T4 eligibility. Governance is
strict (Doc 05 §5.4): self-report is never punitive, never appears in performance
records, and enters the optimizer only as a capacity adjustment code without stated
reason. Agencies uncomfortable with instrumented well-being data can run the model
without it; the adjustment channel (supervisor-entered, reason-free) still exists.

## 3.6 Supervision as a modeled resource

Complex and stretch assignments consume supervisor coaching time, which is finite. Each
case contributes a **supervision intensity** `σ_i` (a simple function of tier and
stretch status: T1/T2 = 1, T3 = 2, T4 = 3, +2 if stretch), and each unit `u` has a
supervision budget `S_u` (scaled by the supervisor's own span of control, admin load,
and experience). The optimizer enforces `Σ_{i→unit u} σ_i x_ij ≤ S_u` (L0). This is the
formal link between the individual level and the supervisor level: a unit full of
novices *cannot* absorb many T4 cases no matter how the arithmetic of κ works out, and
the model must route accordingly (Doc 04 §4.8).

**Scarce-expertise protection.** E4 specialists are the binding resource for T4 work.
The asymmetric surplus discount in match quality (Doc 04 §4.2) already discourages
spending them on routine cases; agencies may additionally reserve a fraction of each
specialist's capacity for T4-tier intake (a simple reserved-capacity constraint).

## 3.7 Update pipeline and data quality

- Computed components (`e_j`, case-history counts, capacity ledger) refresh from
  administrative systems monthly or on event.
- Rated components (skill BARS) refresh semi-annually, after major trainings, and at
  role change; ratings older than 12 months are flagged stale and decay is *not*
  assumed — stale profiles trigger a re-rating task, not a silent penalty.
- Every profile field is visible to the worker; disputes go through the calibration
  conference process (Doc 05 §5.4). A profile the worker has never seen is a governance
  violation, not a convenience.
