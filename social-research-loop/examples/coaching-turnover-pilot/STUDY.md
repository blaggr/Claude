# Phase 1 pilot — AI coaching simulation: caseworker skill & first-year turnover

This is the program's first pilot through the agentic research loop. **Phase 1 is
a dry run**: it exercises the **Frame** and **Design** stages only — producing an
evidence brief and a draft instrument + analysis plan — with **no live or
case-level data**. It validates the loop and yields IRB-ready design materials.

Config: [`config/pilot-coaching-turnover.yaml`](../../config/pilot-coaching-turnover.yaml)

## Research question

> Does an AI coaching/simulation tool improve frontline child-welfare caseworker
> skill acquisition and reduce first-year turnover, and are those effects
> equitable across worker subgroups?

Framework: **Kirkpatrick** (reaction → learning → behavior/transfer → results).

## Researcher seed (humans frame; agents elaborate)

- **Population**: newly hired frontline child-welfare caseworkers, first 12 months.
- **Comparison**: AI-coaching onboarding vs. standard training (quasi-experimental).
- **Hypotheses**:
  - H1 (learning): larger pre/post skill gains for AI-coaching users.
  - H2 (behavior): better on-the-job practice transfer.
  - H3 (results): lower first-year turnover.
  - H4 (equity): no adverse difference in effects across worker subgroups.
- **Constraints**: dry run, no live data; family outcomes deferred to a later cycle.

## How to run

```bash
cd social-research-loop
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...        # required for real agent output

# Stage 1 — Frame (Librarian): evidence brief + refined question/hypotheses
python -m loop.orchestrator --config config/pilot-coaching-turnover.yaml
#   review outputs/run-pilot-00-frame.json, then:
python -m loop.orchestrator --resume pilot --revise "tighten H4 to name the fairness metric"   # optional
python -m loop.orchestrator --resume pilot --approve

# Stage 2 — Design (Methodologist): instrument + analysis plan (with equity plan) + IRB summary
#   review outputs/run-pilot-01-design.json, then:
python -m loop.orchestrator --resume pilot --approve

python -m loop.orchestrator --status pilot
```

Without an API key the loop still runs end-to-end and emits stub outputs, so the
gate flow and state can be verified offline (this is what the test suite does).

## What each gate produces

| Gate | Agent | Output (`outputs/run-pilot-*.json`) | The reviewer checks |
|------|-------|-------------------------------------|---------------------|
| Frame | Librarian | research question, background, known-vs-open, hypotheses, **cited** sources | Are claims cited? Is the question answerable? Is equity (H4) represented? |
| Design | Methodologist | instrument (items tagged to Kirkpatrick levels), sampling, analysis plan **incl. pre-specified subgroup/disparate-impact analysis**, IRB-ready protocol summary, construct-validity notes | Is the instrument valid and unbiased? Is the equity analysis pre-specified? Is the IRB summary complete? |

## Publishing the reference outputs

Run outputs land in `outputs/` (git-ignored). To keep the pilot's Frame and
Design results as a committed **reference example**, copy them next to this file
and commit — they are design artifacts and contain no participant data, so they
are safe to track:

```bash
cp outputs/run-pilot-00-frame.json  examples/coaching-turnover-pilot/frame.json
cp outputs/run-pilot-01-design.json examples/coaching-turnover-pilot/design.json
git add examples/coaching-turnover-pilot/*.json
git commit -m "Add reference Frame/Design outputs for the coaching-turnover pilot"
```

(`examples/` is tracked; only `outputs/` and run state are ignored.)

## Scope of this pilot

Phase 1 stops after Design. Collect → Analyze → Interpret → Report → Recommend
are wired but run in later phases (see `PLAN.md` §10), when a de-identified
worker-survey dataset is connected and the disparate-impact analysis runs on real
data. Family-level outcomes are explicitly deferred to a future cycle and are not
part of this pilot.
