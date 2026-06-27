"""Orchestrator — drives the research loop, stage by stage, with human gates.

Usage:
    python -m loop.orchestrator --new "<research question>" [--id myrun]
    python -m loop.orchestrator --resume <run-id> --approve
    python -m loop.orchestrator --resume <run-id> --revise "<feedback>"
    python -m loop.orchestrator --status <run-id>

Each stage runs its agent, optionally a Critic pass, persists state, and STOPS
at a human gate. The researcher reviews outputs/ then approves to advance.
Stages without an owning agent (collect, recommend) are human/connector steps
and simply pause for the human.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as `python -m loop.orchestrator` or `python orchestrator.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import STAGE_AGENTS, Critic, LLMClient  # noqa: E402
from loop.config import load_config  # noqa: E402
from loop.state import RunState  # noqa: E402

CRITIC_AFTER = {"analyze", "interpret", "report"}


def _llm(state: RunState) -> LLMClient:
    """Build the LLM client from the run's config (falls back to defaults)."""
    if state.config_path and Path(state.config_path).exists():
        cfg = load_config(state.config_path).get("llm", {})
        return LLMClient(
            model=cfg.get("model", "claude-opus-4-8"),
            temperature=cfg.get("temperature", 0.2),
            max_tokens=cfg.get("max_tokens", 4096),
        )
    return LLMClient()


def run_stage(state: RunState) -> RunState:
    """Run the current stage's agent (if any) and pause at its human gate."""
    stage = state.current_stage
    if stage is None:
        print("Run complete.")
        return state

    agent_cls = STAGE_AGENTS.get(stage)
    if agent_cls is None:
        # collect / recommend: human or connector step.
        print(f"[{stage}] human/connector step — no agent. Provide inputs, then --approve.")
        state.status = "pending_gate"
        state.log("stage_paused_for_human", stage=stage)
        state.save()
        return state

    llm = _llm(state)
    agent = agent_cls(llm)

    # Context = question + framework + researcher seed + all prior stage outputs.
    context = {
        "question": state.question,
        "framework": state.framework,
        "seed": state.seed,
        **state.outputs,
    }
    if stage in state.revise:
        context["_revise_feedback"] = state.revise[stage]
    output = agent.run(context)
    state.outputs[stage] = output
    state.log("stage_ran", stage=stage, agent=agent.ROLE)

    if stage in CRITIC_AFTER:
        critic = Critic(llm)
        review = critic.review(stage, output)
        state.critic[stage] = review
        state.log("critic_reviewed", stage=stage, flagged=review.get("flagged"))
        if review.get("flagged"):
            print(f"[{stage}] ⚠ Critic flagged this output — review before approving.")

    state.status = "pending_gate"
    out_path = _write_output(state, stage, output)
    print(f"[{stage}] done → {out_path}\nReview, then: --resume {state.run_id} --approve")
    state.save()
    return state


def _write_output(state: RunState, stage: str, output: dict) -> Path:
    import json

    out_dir = Path(__file__).resolve().parent.parent / "outputs"
    out_dir.mkdir(exist_ok=True)
    p = out_dir / f"run-{state.run_id}-{state.current_stage_index:02d}-{stage}.json"
    p.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return p


def cmd_new(args: argparse.Namespace) -> None:
    run_id = args.id or "001"
    state = RunState(run_id=run_id, question=args.new, framework=args.framework)
    state.log("run_created", question=args.new)
    state.save()
    print(f"Created run {run_id}. Running first stage...")
    run_stage(state)


# Researcher-provided keys copied from a config's `project` block into the seed.
SEED_KEYS = ("hypotheses", "population", "constraints", "comparison")


def cmd_config(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    proj = cfg.get("project", {})
    if not proj.get("question"):
        raise ValueError(f"{args.config} has no project.question to run.")
    run_id = args.id or "pilot"
    state = RunState(
        run_id=run_id,
        question=proj["question"],
        framework=proj.get("framework", "kirkpatrick"),
        config_path=str(Path(args.config).resolve()),
        seed={k: proj[k] for k in SEED_KEYS if k in proj},
    )
    state.log("run_created_from_config", config=args.config, project=proj.get("name"))
    state.save()
    print(f"Created run {run_id} from {args.config}. Running first stage...")
    run_stage(state)


def cmd_resume(args: argparse.Namespace) -> None:
    state = RunState.load(args.resume)
    if args.revise:
        # Re-run current stage with feedback appended.
        stage = state.current_stage
        state.revise[stage] = args.revise
        state.log("revise_requested", stage=stage, feedback=args.revise)
        run_stage(state)
    elif args.approve:
        state.log("gate_approved", stage=state.current_stage)
        state.advance()
        state.save()
        run_stage(state)
    else:
        print("Specify --approve or --revise '<feedback>'.")


def cmd_status(args: argparse.Namespace) -> None:
    state = RunState.load(args.status)
    print(f"Run {state.run_id}: stage={state.current_stage} status={state.status}")
    print(f"Completed stages: {list(state.outputs.keys())}")
    flagged = [s for s, r in state.critic.items() if r.get("flagged")]
    if flagged:
        print(f"Critic-flagged: {flagged}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Agentic research loop orchestrator")
    p.add_argument("--new", metavar="QUESTION", help="start a new run with this research question")
    p.add_argument("--config", metavar="PATH", help="start a new run from a config YAML (uses project.question)")
    p.add_argument("--id", help="run id (default 001, or 'pilot' for --config)")
    p.add_argument("--framework", default="kirkpatrick", help="evaluation framework (with --new)")
    p.add_argument("--resume", metavar="RUN_ID", help="resume an existing run")
    p.add_argument("--approve", action="store_true", help="approve the current gate and advance")
    p.add_argument("--revise", metavar="FEEDBACK", help="re-run current stage with feedback")
    p.add_argument("--status", metavar="RUN_ID", help="show run status")
    args = p.parse_args(argv)

    if args.new:
        cmd_new(args)
    elif args.config:
        cmd_config(args)
    elif args.resume:
        cmd_resume(args)
    elif args.status:
        cmd_status(args)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
