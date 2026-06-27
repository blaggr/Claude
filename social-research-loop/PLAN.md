# Agentic Research Loop — Plan

A plan for building a semi-autonomous, agent-driven research loop for an
**applied social research program** (program evaluation, workforce-training
research, survey-based field studies). The system orchestrates a small fleet of
specialized AI agents through the full applied-research cycle, with a human
researcher in the loop at every decision gate.

> Scope note: this is a planning + scaffolding deliverable. The code in this
> project is a runnable skeleton with clear extension points, not a finished
> product. The roadmap below sequences the build.

---

## 1. Goals & non-goals

### Goals
- Compress the slow parts of the applied-research cycle (literature triage,
  instrument drafting, cleaning, first-pass analysis, reporting) without
  removing researcher judgment.
- Make every output **auditable and reproducible**: every claim traces to a
  source, a dataset row, or an analysis step.
- Bake in **research ethics and human-subjects protections** from the start
  (consent, de-identification, IRB alignment), not as an afterthought.
- Produce artifacts in the formats the program already uses (Kirkpatrick-framed
  evaluation reports, Qualtrics-sourced datasets, stakeholder briefs).

### Non-goals
- Not a fully autonomous researcher. A human approves the research question,
  the instrument, the analysis plan, and the final report.
- Not a replacement for IRB review or statistical expertise.
- Not a general-purpose chatbot — it is a structured pipeline.

---

## 2. The applied-research loop

The system models the applied social research cycle as an explicit, resumable
loop. Each stage has an owning agent, defined inputs/outputs, and a human gate.

```
        ┌──────────────────────────────────────────────────────────┐
        │                                                            │
        ▼                                                            │
  (1) FRAME ──▶ (2) DESIGN ──▶ (3) COLLECT ──▶ (4) ANALYZE ──▶ (5) INTERPRET
   question      instrument     data (Qualtrics)   stats          vs. framework
   & lit scan    & method                                              │
        ▲                                                              ▼
        │                                                       (6) REPORT
        │                                                              │
        └────────────── (7) RECOMMEND / next cycle ◀───────────────────┘
```

| # | Stage | Owning agent | Key output | Human gate |
|---|-------|--------------|------------|------------|
| 1 | Frame | Librarian | Research question, evidence brief, hypotheses | Approve question & scope |
| 2 | Design | Methodologist | Survey/instrument draft, analysis plan, sampling | Approve instrument (pre-IRB) |
| 3 | Collect | (human + connectors) | Cleaned, de-identified dataset | Confirm data quality |
| 4 | Analyze | Analyst | Statistics, tables, figures, assumptions checks | Review analysis |
| 5 | Interpret | Interpreter | Findings mapped to framework (e.g. Kirkpatrick) | Validate interpretation |
| 6 | Report | Writer | Stakeholder report / brief + methods appendix | Approve for release |
| 7 | Recommend | Writer + Critic | Recommendations, limitations, next-cycle questions | Decide next iteration |

A **Critic agent** runs across stages as an adversarial reviewer (see §4).

---

## 3. Why "agentic loop" and not a single prompt

- **Separation of concerns.** A methodologist that designs instruments should
  not also grade its own analysis. Distinct agents with distinct system prompts
  produce sharper, less self-confirming output.
- **Adversarial verification.** A dedicated Critic tries to *refute* each
  finding before it reaches a human. This is the single biggest quality lever
  against plausible-but-wrong conclusions.
- **Resumability.** The loop persists state between stages, so a run can pause
  at a human gate for days and resume cleanly.
- **Iteration.** Stage 7 feeds back into stage 1 — recommendations and
  open questions seed the next research cycle.

---

## 4. Agent roster

Each agent = a system prompt (`prompts/`) + a thin Python wrapper (`agents/`)
+ a JSON-shaped contract for its output.

- **Librarian** — scans literature/evidence, frames the question, drafts
  hypotheses, flags what is already known vs. genuinely open.
- **Methodologist** — drafts instruments (survey items, interview guides),
  proposes sampling and an analysis plan, checks construct validity and
  alignment to the evaluation framework.
- **Analyst** — runs/produces the analysis (descriptives, group comparisons,
  reliability, effect sizes), states and checks assumptions, generates tables
  and figures, and emits a structured results object.
- **Interpreter** — maps results onto the program's framework (e.g. the four
  Kirkpatrick levels: reaction → learning → behavior/transfer → results),
  separating signal from noise and stating confidence.
- **Writer** — synthesizes a stakeholder-ready report and a technical methods
  appendix; produces recommendations and limitations.
- **Critic** — adversarial reviewer invoked after Analyze, Interpret, and
  Report. Defaults to skepticism: tries to find the unsupported claim, the
  confound, the over-reach, the missing limitation. A finding survives only if
  the Critic cannot refute it.

---

## 5. Architecture

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
  is the Claude API (latest Claude models); see `docs/ARCHITECTURE.md`. Keys are
  read from the environment so the modules import without secrets.
- **Connectors** (future): Qualtrics export, file ingest, citation lookup. The
  Qualtrics→Kirkpatrick analysis already exists as a Claude Code skill and is
  the model for the Collect/Analyze connector.

### Data flow & storage
- `data/` — raw and cleaned datasets (git-ignored; never commit PII).
- `instruments/` — versioned survey/interview instruments.
- `outputs/` — generated briefs, reports, tables, figures (run-stamped).

---

## 6. Ethics, privacy & reproducibility (first-class)

Applied social research touches human subjects, so these are requirements, not
nice-to-haves. Detail in `docs/ETHICS.md`.

- **Human subjects / IRB**: the loop produces an IRB-ready protocol summary at
  the Design gate; no data collection proceeds in the system before approval is
  recorded.
- **De-identification**: data enters the loop only after PII is stripped;
  `data/` is git-ignored by default.
- **Consent & data use**: instruments carry consent language; data use is
  scoped to the approved question.
- **Reproducibility**: every report ships with a methods appendix and an audit
  trail (which agent, which prompt version, which inputs produced each claim).
- **AI disclosure**: reports disclose AI assistance and the human-review gates.

---

## 7. Tech stack

- **Language**: Python 3.11+.
- **LLM**: Claude API (latest models) via a provider-agnostic adapter.
- **Config**: YAML.
- **Validation**: structured (JSON-schema-shaped) agent outputs.
- **Stats** (Analyze stage, later phase): pandas, scipy/statsmodels.
- **Reporting**: Markdown → HTML (the existing AWE dashboard skill is the
  template for self-contained HTML reports).

Deliberately lightweight: no heavyweight agent framework. The orchestrator is
plain Python so the control flow stays inspectable.

---

## 8. Roadmap (phased)

**Phase 0 — Scaffold (this commit).** Repo structure, plan, agent prompts,
orchestrator skeleton, ethics doc.

**Phase 1 — Frame + Design, dry run.** Wire the LLM client; make Librarian and
Methodologist produce a real evidence brief and instrument draft from a typed
research question. Human gates working. No live data.

**Phase 2 — Analyze on real data.** Connect a de-identified Qualtrics export
(reuse the AWE skill's logic); Analyst produces descriptives + group
comparisons with assumption checks; Interpreter maps to Kirkpatrick.

**Phase 3 — Report + Critic.** Writer emits a stakeholder report + methods
appendix; Critic runs adversarial review on Analyze/Interpret/Report.

**Phase 4 — Loop closure & resumability.** Stage 7 recommendations seed a new
cycle; full resumable state; run-stamped outputs; HTML rendering.

**Phase 5 — Hardening.** Tests, prompt versioning, reproducibility audit,
optional batch/scheduled runs.

---

## 9. Success metrics

- **Cycle time**: time from question → reviewed draft report (target: large
  reduction vs. current manual process).
- **Trust**: % of agent claims that survive Critic + human review unchanged.
- **Traceability**: % of report claims with an explicit source/data/step link
  (target: 100%).
- **Reuse**: instruments and analysis plans reused across cycles.

---

## 10. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Hallucinated findings / citations | Critic adversarial pass + mandatory source links; human gate before release |
| PII leakage | De-identify before ingest; `data/` git-ignored; no PII in prompts |
| Over-automation erodes judgment | Human gate at every stage; agents propose, humans decide |
| Statistical misuse | Analyst states assumptions; Critic checks them; human/stats review at Analyze gate |
| Prompt drift across runs | Version prompts; record prompt version in audit trail |

---

## 11. How to use this scaffold

See `README.md` for the file map and `docs/ARCHITECTURE.md` for the
orchestrator/agent contract. `python -m loop.orchestrator --help` shows the
stage-runner skeleton.
