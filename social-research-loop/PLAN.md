# Agentic Research Loop — Plan

A plan for building a semi-autonomous, agent-driven research loop for an
**applied social research program studying the application of AI in child
welfare and human services workforce development**.

The program's research questions concern how AI tools — predictive risk models,
decision-support systems, documentation assistants, training/coaching
simulations — affect the **human services workforce** (frontline caseworkers,
supervisors, and the families they serve): skill acquisition, decision quality
and consistency, trust and adoption, workload and burnout, retention/turnover,
and **equity of outcomes across the families served**.

The system orchestrates a small fleet of specialized AI agents through the full
applied-research cycle, with a human researcher in the loop at every decision
gate. It is, deliberately, AI studying the responsible use of AI in one of the
highest-stakes domains of public human services.

> Scope note: this is a planning + scaffolding deliverable. The code in this
> project is a runnable skeleton with clear extension points, not a finished
> product. The roadmap below sequences the build.

---

## 1. The research domain

**Child welfare** and the broader **human services** system are characterized by
high-stakes decisions about vulnerable people, chronic workforce shortages, high
caseworker turnover, and a fast-growing wave of AI deployments. Common AI
applications under study include:

- **Predictive risk modeling (PRM)** and decision support at hotline screening
  and case planning.
- **Documentation / administrative-burden automation** (note-taking, summaries).
- **Training, coaching, and simulation** tools for workforce development.
- **Workload and quality-assurance** analytics.

These applications raise recurring, researchable questions about effectiveness,
adoption, workforce impact, and — centrally — **algorithmic equity and the
rights of the families served**. The loop is built so that equity and
responsible-AI scrutiny are not optional add-ons but structural.

### Illustrative research questions the loop is designed to run
- Does an AI coaching/simulation tool improve frontline caseworker skill
  acquisition and reduce first-year turnover?
- How does an AI-assisted screening tool affect the consistency *and equity* of
  hotline screening decisions across racial/ethnic and socioeconomic groups?
- What are caseworkers' trust, adoption, and workload outcomes when an AI
  documentation assistant is deployed in a human services agency?
- Where do frontline workers override or defer to AI recommendations, and with
  what consequences for families?

---

## 2. Goals & non-goals

### Goals
- Compress the slow parts of the applied-research cycle (literature triage,
  instrument drafting, cleaning, first-pass analysis, reporting) without
  removing researcher judgment.
- Make **algorithmic equity and workforce impact** first-class outcomes in every
  study, not afterthoughts.
- Make every output **auditable and reproducible**: every claim traces to a
  source, a dataset row, or an analysis step.
- Bake in **research ethics and protections for vulnerable populations**
  (consent, de-identification, IRB alignment, disparate-impact analysis) from
  the start.
- Produce artifacts in the formats the program already uses (framework-mapped
  evaluation reports, Qualtrics-/admin-data-sourced datasets, agency briefs).

### Non-goals
- Not a fully autonomous researcher. A human approves the research question,
  the instrument, the analysis plan, and the final report.
- **Not a tool for building, scoring, or operating any child-welfare AI system**,
  and not a substitute for the human judgment of caseworkers or courts. It
  *studies* such systems; it does not make case decisions.
- Not a replacement for IRB review or statistical/methodological expertise.

---

## 3. The applied-research loop

The system models the applied social research cycle as an explicit, resumable
loop. Each stage has an owning agent, defined inputs/outputs, and a human gate.

```
        ┌──────────────────────────────────────────────────────────┐
        │                                                            │
        ▼                                                            │
  (1) FRAME ──▶ (2) DESIGN ──▶ (3) COLLECT ──▶ (4) ANALYZE ──▶ (5) INTERPRET
   question      instrument     data (survey/    stats +          vs. framework
   & lit scan    & method        admin data)    equity audit       + equity
        ▲                                                              │
        │                                                              ▼
        │                                                       (6) REPORT
        │                                                              │
        └────────────── (7) RECOMMEND / next cycle ◀───────────────────┘
```

| # | Stage | Owning agent | Key output | Human gate |
|---|-------|--------------|------------|------------|
| 1 | Frame | Librarian | Research question, evidence brief, hypotheses | Approve question & scope |
| 2 | Design | Methodologist | Instrument, analysis plan (incl. subgroup/equity plan), sampling | Approve instrument (pre-IRB) |
| 3 | Collect | (human + connectors) | Cleaned, de-identified dataset | Confirm data quality |
| 4 | Analyze | Analyst | Statistics, tables, figures, assumption checks, disparate-impact analysis | Review analysis |
| 5 | Interpret | Interpreter | Findings mapped to framework + equity findings | Validate interpretation |
| 6 | Report | Writer | Agency/stakeholder report + methods appendix | Approve for release |
| 7 | Recommend | Writer + Critic | Recommendations, limitations, next-cycle questions | Decide next iteration |

A **Critic agent** runs across stages as an adversarial reviewer with an
explicit algorithmic-equity lens (see §5).

---

## 4. Evaluation frameworks

The research focus spans *workforce development* (training interventions) and
*implementation of AI tools* (deploying a system in real agency practice), so the
loop supports several frameworks, selectable per study (`project.framework`):

- **kirkpatrick** — training/coaching interventions: reaction → learning →
  behavior/transfer → results. (The program's existing default for workforce
  training evaluation.)
- **reaim** — implementation of an AI tool in practice: Reach, Effectiveness,
  Adoption, Implementation, Maintenance.
- **cfir** — barriers/facilitators of adoption (Consolidated Framework for
  Implementation Research).
- **responsible_ai** — a cross-cutting equity/responsibility lens applied to
  *every* study: fairness/disparate impact, transparency, accountability, human
  oversight, and validity-in-context.

The Interpreter maps results onto the chosen framework; the responsible-AI lens
is always also applied because the families served bear the cost of failures.

---

## 5. Why "agentic loop" and not a single prompt

- **Separation of concerns.** A methodologist that designs instruments should
  not also grade its own analysis. Distinct agents produce sharper, less
  self-confirming output.
- **Adversarial + equity verification.** A dedicated Critic tries to *refute*
  each finding before it reaches a human, and specifically probes for
  unexamined disparate impact, confounded subgroup effects, and over-claims
  about AI benefit. This is the single biggest quality lever in a domain where
  a plausible-but-wrong conclusion can harm families.
- **Resumability.** The loop persists state between stages, so a run can pause
  at a human gate for days and resume cleanly.
- **Iteration.** Stage 7 feeds back into stage 1 — recommendations and open
  questions seed the next research cycle.

---

## 6. Agent roster

Each agent = a system prompt (`prompts/`) + a thin Python wrapper (`agents/`)
+ a JSON-shaped contract for its output.

- **Librarian** — scans literature/evidence on AI in child welfare and human
  services workforce development; frames the question; drafts hypotheses; flags
  what is established (e.g. known PRM equity findings) vs. genuinely open.
- **Methodologist** — drafts instruments (worker surveys, interview guides,
  observation protocols), proposes sampling and an analysis plan that
  **includes a pre-specified subgroup/equity analysis**, and checks construct
  validity and framework alignment.
- **Analyst** — produces the analysis (descriptives, group comparisons,
  reliability, effect sizes) and a **disparate-impact analysis across the
  protected/served subgroups**, states and checks assumptions, generates tables
  and figures, and emits a structured results object. Never invents numbers.
- **Interpreter** — maps results onto the chosen framework AND the
  responsible-AI lens, separating signal from noise, stating confidence, and
  refusing to infer outcomes for one group from another.
- **Writer** — synthesizes an agency-ready report and a technical methods
  appendix; produces recommendations, limitations, and an AI-assistance
  disclosure.
- **Critic** — adversarial reviewer invoked after Analyze, Interpret, and
  Report. Defaults to skepticism; specifically hunts unsupported AI-benefit
  claims, unexamined disparate impact, confounds, over-reach, and missing
  limitations. A finding survives only if the Critic cannot refute it.

> Roadmap option: promote the equity lens to a dedicated **Equity Reviewer**
> agent if studies routinely demand deeper fairness audits than the Critic's
> cross-cutting pass provides.

---

## 7. Architecture

```
config/loop.yaml ──▶ loop/orchestrator.py ──▶ agents/*  ──▶ outputs/
                          │                      │
                          ▼                      ▼
                     loop/state.py          prompts/*.md
                  (resumable run state)   (system prompts)
```

- **Orchestrator** (`loop/orchestrator.py`): drives the stage sequence, calls
  agents, persists state, and stops at human gates.
- **State** (`loop/state.py`): a JSON run-state file per research project —
  records stage, agent outputs, approvals, and an audit trail. Resumable.
- **Agents** (`agents/`): each wraps one prompt and one LLM call, returns a
  validated structured object.
- **LLM client** (`agents/base.py`): provider-agnostic adapter. Default target
  is the Claude API (latest Claude models). Keys are read from the environment
  so the modules import without secrets.
- **Connectors** (future): survey export (Qualtrics), de-identified
  administrative-data ingest, citation lookup. The existing
  Qualtrics→framework analysis Claude Code skill is the model for the
  Collect/Analyze connector.

### Data flow & storage
- `data/` — raw and cleaned datasets (git-ignored; never commit PII or
  case-level child-welfare data).
- `instruments/` — versioned survey/interview/observation instruments.
- `outputs/` — generated briefs, reports, tables, figures (run-stamped).

---

## 8. Ethics, equity, privacy & reproducibility (first-class)

Research in child welfare touches **vulnerable populations** — children,
families under state scrutiny, and a frontline workforce — so these are
requirements, not nice-to-haves. Detail in `docs/ETHICS.md`.

- **Vulnerable populations & IRB**: studies involving families, case data, or
  workers go through IRB; the loop produces an IRB-ready protocol summary at the
  Design gate and blocks data ingest until approval is recorded.
- **Algorithmic equity**: every study pre-specifies and reports a
  disparate-impact analysis across served subgroups. The Critic refuses to pass
  AI-benefit claims that ignore equity.
- **De-identification**: data enters the loop only after PII/case identifiers
  are stripped; `data/` is git-ignored. No case-level identifiers in prompts.
- **No operational use**: outputs inform research and policy, not individual
  case decisions. The system never scores or screens a real family.
- **Reproducibility**: every report ships with a methods appendix and an audit
  trail (which agent, which prompt version, which inputs produced each claim).
- **AI disclosure**: reports disclose AI assistance and the human-review gates,
  appropriate for a program studying responsible AI use.

---

## 9. Tech stack

- **Language**: Python 3.11+.
- **LLM**: Claude API (latest models) via a provider-agnostic adapter.
- **Config**: YAML.
- **Validation**: structured (JSON-schema-shaped) agent outputs.
- **Stats** (Analyze stage): pandas, scipy/statsmodels; fairness metrics for
  disparate-impact analysis.
- **Reporting**: Markdown → HTML (the existing AWE dashboard skill is the
  template for self-contained HTML reports).

Deliberately lightweight: no heavyweight agent framework. The orchestrator is
plain Python so the control flow stays inspectable — itself a transparency
property worth modeling in this domain.

---

## 10. Roadmap (phased)

**Phase 0 — Scaffold (current).** Repo structure, plan, agent prompts,
orchestrator skeleton, ethics doc — refocused on AI in child welfare & human
services workforce development.

**Phase 1 — Frame + Design, dry run.** Wire the LLM client; Librarian and
Methodologist produce a real evidence brief and instrument draft (with a
pre-specified equity analysis plan) from a typed research question. Human gates
working. No live data.

**Phase 2 — Analyze on real data.** Connect a de-identified worker survey /
admin export; Analyst produces descriptives, group comparisons, and a
disparate-impact analysis; Interpreter maps to the chosen framework + equity.

**Phase 3 — Report + Critic.** Writer emits an agency report + methods appendix;
Critic runs adversarial + equity review on Analyze/Interpret/Report.

**Phase 4 — Loop closure & resumability.** Stage 7 recommendations seed a new
cycle; full resumable state; run-stamped outputs; HTML rendering.

**Phase 5 — Hardening.** Tests, prompt versioning, reproducibility audit,
optional dedicated Equity Reviewer agent, optional scheduled runs.

---

## 11. Success metrics

- **Cycle time**: question → reviewed draft report (target: large reduction vs.
  the current manual process).
- **Trust**: % of agent claims that survive Critic + human review unchanged.
- **Equity coverage**: % of studies with a completed, pre-specified
  disparate-impact analysis (target: 100%).
- **Traceability**: % of report claims with an explicit source/data/step link
  (target: 100%).
- **Reuse**: instruments and analysis plans reused across cycles.

---

## 12. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Hallucinated findings / citations | Critic adversarial pass + mandatory source links; human gate before release |
| Unexamined disparate impact on families | Pre-specified subgroup/equity analysis; Critic equity lens; equity-coverage metric |
| Over-claiming AI benefit | Analyst reports effect sizes + uncertainty; Critic refutes benefit claims that ignore harms/equity |
| PII / case-data leakage | De-identify before ingest; `data/` git-ignored; no case identifiers in prompts |
| Over-automation erodes judgment | Human gate at every stage; agents propose, humans decide |
| Statistical misuse | Analyst states assumptions; Critic checks them; human/stats review at Analyze gate |
| Mistaken operational use | Explicit non-goal; outputs are research, never case decisions |

---

## 13. How to use this scaffold

See `README.md` for the file map and `docs/ARCHITECTURE.md` for the
orchestrator/agent contract. `python -m loop.orchestrator --help` shows the
stage-runner skeleton.
