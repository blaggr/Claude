"""Critic — adversarial reviewer invoked after Analyze, Interpret, and Report.

The Critic's job is to *refute*, not to praise. It defaults to skepticism: a
finding survives only if the Critic cannot mount a credible refutation. With
multiple votes, a finding is flagged unless a majority of passes fail to refute.
"""
from __future__ import annotations

from typing import Any

from .base import Agent


class Critic(Agent):
    ROLE = "critic"
    OUTPUT_SCHEMA = {
        "refuted": "bool",
        "issues": "list",
        "unsupported_claims": "list",
        "missing_limitations": "list",
        "verdict": "str",
    }

    def build_user_prompt(self, context: dict[str, Any]) -> str:
        return (
            "You are an adversarial reviewer. Try to REFUTE the output below. "
            "Hunt for unsupported claims, confounds, mis-stated statistics, "
            "over-reach, and missing limitations. Default to refuted=true if "
            "you are uncertain the conclusions are fully supported.\n\n"
            f"Stage under review: {context.get('stage', '')}\n"
            f"Output under review: {context.get('output', {})}\n\n"
            "Return JSON with keys: refuted (bool), issues (list), "
            "unsupported_claims (list), missing_limitations (list), verdict."
        )

    def review(self, stage: str, output: dict[str, Any], votes: int = 3) -> dict[str, Any]:
        """Run `votes` independent passes; flag unless a majority fail to refute."""
        results = [self.run({"stage": stage, "output": output}) for _ in range(votes)]
        refuted = sum(1 for r in results if r.get("refuted")) > votes / 2
        return {"flagged": refuted, "passes": results}
