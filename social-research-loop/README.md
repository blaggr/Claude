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
│   ├── loop.example.yaml             # annotated example configuration
│   └── pilot-coaching-turnover.yaml  # Phase 1 pilot study config
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
│   ├── config.py           # loads run config YAML
│   └── state.py            # resumable run state + audit trail
├── prompts/                # system prompts (one per agent)
├── tests/                  # test suite (runs without an API key)
├── examples/
│   └── coaching-turnover-pilot/STUDY.md   # the Phase 1 pilot, documented
├── instruments/            # versioned survey/interview instruments
├── data/                   # datasets (git-ignored — never commit PII)
├── outputs/                # generated reports/figures (run-stamped)
└── docs/
    ├── ARCHITECTURE.md     # orchestrator + agent contract
    └── ETHICS.md           # IRB / consent / de-identification / reproducibility
```

## Status

**Phase 1 — in progress.** The LLM client is wired to the Claude API, runs are
config-driven, the revise/approve human gates work, and a test suite covers the
wiring. The active pilot is the **AI coaching → caseworker skill & turnover**
study (Frame + Design, dry run, no live data) — see
[`examples/coaching-turnover-pilot/STUDY.md`](examples/coaching-turnover-pilot/STUDY.md).
Later stages (Analyze onward) are wired but run in Phase 2+. Roadmap: `PLAN.md` §10.

## Quick start

```bash
cd social-research-loop
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...                 # required for real agent output

# Run the pilot study from its config:
python -m loop.orchestrator --config config/pilot-coaching-turnover.yaml
python -m loop.orchestrator --resume pilot --approve      # review outputs/, then advance
python -m loop.orchestrator --status pilot

# Or start an ad-hoc run from a question:
python -m loop.orchestrator --new "Your research question" --framework reaim
```

Each stage stops at a human gate. Resume with `--resume <run-id> --approve`, or
`--resume <run-id> --revise "<feedback>"` to re-run the stage with feedback.
Without an API key the loop runs end-to-end in stub mode (used by the tests).

```bash
python -m unittest discover tests -v         # run the test suite (no key needed)
```

## Ethics

This system handles human-subjects research data about **vulnerable populations**
(children, families under state scrutiny, and a frontline workforce) and the AI
systems used on them. Every study pre-specifies a disparate-impact analysis.
Read `docs/ETHICS.md` before connecting real data. `data/` is git-ignored by
default — never commit PII or case-level child-welfare data.
