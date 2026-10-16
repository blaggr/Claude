"""Writer — Stage 6 (Report) + Stage 7 (Recommend)."""
from __future__ import annotations

from typing import Any

from .base import Agent


class Writer(Agent):
    ROLE = "writer"
    OUTPUT_SCHEMA = {
        "executive_summary": "str",
        "report_markdown": "str",
        "methods_appendix": "str",
        "recommendations": "list",
        "limitations": "list",
        "next_cycle_questions": "list",
    }

    def build_user_prompt(self, context: dict[str, Any]) -> str:
        return (
            "Write a stakeholder-ready evaluation report plus a technical "
            "methods appendix. Every claim must trace to a finding or data "
            "point. Include recommendations, honest limitations, and questions "
            "that seed the next research cycle. Add an AI-assistance disclosure "
            "and note the human-review gates.\n\n"
            f"Interpretation: {context.get('interpret', {})}\n"
            f"Analysis: {context.get('analyze', {})}\n"
            f"Design (for methods appendix): {context.get('design', {})}\n\n"
            "Return JSON with keys: executive_summary, report_markdown, "
            "methods_appendix, recommendations (list), limitations (list), "
            "next_cycle_questions (list)."
        )
