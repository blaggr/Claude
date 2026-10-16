"""Methodologist — Stage 2 (Design): instrument, sampling, analysis plan."""
from __future__ import annotations

from typing import Any

from .base import Agent


class Methodologist(Agent):
    ROLE = "methodologist"
    OUTPUT_SCHEMA = {
        "instrument": "list",
        "sampling": "str",
        "analysis_plan": "str",
        "irb_summary": "str",
        "construct_validity_notes": "str",
    }

    def build_user_prompt(self, context: dict[str, Any]) -> str:
        frame = context.get("frame", {})
        seed = context.get("seed", {})
        return (
            "Design the study. Draft an instrument aligned to the question and "
            "framework, propose a sampling approach and an analysis plan that "
            "INCLUDES a pre-specified subgroup/disparate-impact analysis, and "
            "produce an IRB-ready protocol summary.\n\n"
            f"Research question: {frame.get('research_question', '')}\n"
            f"Hypotheses: {frame.get('hypotheses', [])}\n"
            f"Population: {seed.get('population', 'see question')}\n"
            f"Comparison/constraints: {seed.get('comparison', '')} {seed.get('constraints', '')}\n"
            f"Framework: {context.get('framework', 'kirkpatrick')}\n\n"
            "Return JSON with keys: instrument (list of items, each tagged with "
            "the construct/framework level it measures), sampling, analysis_plan, "
            "irb_summary, construct_validity_notes."
        )
