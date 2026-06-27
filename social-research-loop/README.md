# social-research-loop

An **agentic research loop** for an applied social research program studying
**the application of AI in child welfare and human services workforce
development** — a semi-autonomous pipeline of specialized AI agents that move a
study through the full applied-research cycle (frame → design → collect →
analyze → interpret → report → recommend), with a human researcher approving
every gate.

It studies how AI tools (predictive risk models, decision support,
documentation assistants, training/coaching simulations) affect the human
services workforce and the families served — skill, decision quality, trust,
adoption, workload, turnover, and **equity of outcomes**. Algorithmic equity and
protections for vulnerable populations are structural, not optional. Frameworks
supported: Kirkpatrick, RE-AIM, CFIR, and a cross-cutting responsible-AI lens.

📋 **Start with [`PLAN.md`](PLAN.md)** — it is the primary deliverable: goals,
the research loop, agent roster, architecture, ethics, and a phased roadmap.

## File map

```
social-research-loop/
├── PLAN.md                 # ← the plan (read this first)
├── README.md               # this file
├── requirements.txt
├── config/
│   └── loop.example.yaml   # example run configuration
├── agents/                 # one thin wrapper per agent role
│   ├── base.py             # provider-agnostic LLM adapter + Agent base class
│   ├── librarian.py        # (1) frame: question + evidence brief
│   ├── methodologist.py    # (2) design: instrument + analysis plan
│   ├── analyst.py          # (4) analyze: stats, tables, disparate-impact analysis
│   ├── interpreter.py      # (5) interpret: map to framework + responsible-AI/equity lens
│   ├── writer.py           # (6) report: stakeholder brief + appendix
│   └── critic.py           # adversarial reviewer (runs across stages)
├── loop/
│   ├── orchestrator.py     # drives the stage sequence + human gates
│   └── state.py            # resumable run state + audit trail
├── prompts/                # system prompts (one per agent)
├── instruments/            # versioned survey/interview instruments
├── data/                   # datasets (git-ignored — never commit PII)
├── outputs/                # generated reports/figures (run-stamped)
└── docs/
    ├── ARCHITECTURE.md     # orchestrator + agent contract
    └── ETHICS.md           # IRB / consent / de-identification / reproducibility
```

## Status

**Phase 0 — scaffold.** Structure, plan, prompts, and a runnable skeleton are in
place. Agents return stubbed structured output until the LLM client is wired
(Phase 1). See the roadmap in `PLAN.md` §8.

## Quick start

```bash
cd social-research-loop
pip install -r requirements.txt
python -m loop.orchestrator --help          # show the stage runner
python -m loop.orchestrator --new "Does an AI coaching simulation improve frontline caseworker skill and reduce first-year turnover?" --framework kirkpatrick
```

This creates a resumable run and executes stage 1 (Frame). Each subsequent
stage stops at a human gate; resume with `--resume <run-id> --approve`.

## Ethics

This system handles human-subjects research data about **vulnerable populations**
(children, families under state scrutiny, and a frontline workforce) and the AI
systems used on them. Every study pre-specifies a disparate-impact analysis.
Read `docs/ETHICS.md` before connecting real data. `data/` is git-ignored by
default — never commit PII or case-level child-welfare data.
