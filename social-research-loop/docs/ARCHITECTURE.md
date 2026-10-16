# Architecture

## Overview

The system is a plain-Python orchestrator that drives a fixed sequence of
research **stages**, each owned by one **agent**. State is persisted between
stages so a run can pause at a human gate and resume later. There is no
heavyweight agent framework — control flow stays in `loop/orchestrator.py` and
is meant to be read.

```
config/loop.yaml
      │
      ▼
loop/orchestrator.py ──reads/writes──▶ loop/state.py  (run-<id>.json)
      │
      │  for each stage:
      ▼
agents/<role>.py ──uses──▶ agents/base.LLMClient ──▶ Claude API
      │           ──reads──▶ prompts/<role>.md
      ▼
structured output (dict) ──▶ recorded in state + written to outputs/
```

## The agent contract

Every agent subclasses `agents.base.Agent` and implements `run(context)`:

- **Input**: a `context` dict containing the run's accumulated state
  (prior stage outputs, the research question, config).
- **System prompt**: loaded from `prompts/<role>.md`.
- **Output**: a plain `dict` matching that agent's declared `OUTPUT_SCHEMA`.
  The base class validates shape before returning, so downstream stages can
  rely on the contract.

Agents never call each other directly — the orchestrator passes outputs along.
This keeps the dependency graph explicit and the loop resumable.

## Human gates

After each stage the orchestrator stops (unless `auto_approve`). The researcher
reviews the stage output (in `outputs/`), then resumes:

```
python -m loop.orchestrator --resume <run-id> --approve
python -m loop.orchestrator --resume <run-id> --revise "tighten the sampling frame"
```

`--revise` re-runs the current stage with the feedback appended to context;
`--approve` advances to the next stage.

## The Critic

The Critic is not a stage; it is invoked by the orchestrator after the stages
listed in `critic.run_after`. It receives the just-produced output and is
prompted to **refute** it. With `critic.votes: N`, it runs N independent passes;
a finding is flagged for human attention unless a majority fail to refute it.
This is the adversarial-verification pattern: cheap, and the main defense
against confident-but-wrong output.

## State & audit trail

`loop/state.py` persists one JSON file per run under `loop/state/`:

- current stage and status (`pending_gate`, `approved`, `done`)
- every agent output, keyed by stage
- approvals (who/when) and revise feedback
- prompt version used per stage (for reproducibility)

Because all of this is on disk, runs survive process restarts and are auditable
after the fact — a requirement for research reproducibility.

## LLM adapter

`agents/base.LLMClient` is provider-agnostic and supports **OpenAI** and the
**Claude API**, selected via `llm.provider` in config (`openai` | `anthropic`).
The matching key is read from the environment (`OPENAI_API_KEY` /
`ANTHROPIC_API_KEY`); the OpenAI path uses JSON-object response mode, the
Anthropic path concatenates text blocks. Modules import cleanly without a key or
SDK — both are only required at call time, and without a key `complete()` returns
a stub so the loop runs offline. The pilot is configured for OpenAI (`gpt-4o`).

## Extension points

- **Connectors** (`agents/` or a future `connectors/`): Qualtrics export, file
  ingest, citation lookup. The existing Qualtrics→Kirkpatrick Claude Code skill
  is the reference implementation for the Collect/Analyze path.
- **Frameworks**: `interpreter.py` selects a mapping by `project.framework`
  (Kirkpatrick today; logic-model / custom are pluggable).
- **Reporting**: Writer emits Markdown; an HTML renderer (modeled on the AWE
  dashboard skill) is a later phase.
