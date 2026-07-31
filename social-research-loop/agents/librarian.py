"""Librarian — Stage 1 (Frame): question, evidence brief, hypotheses."""
from __future__ import annotations

from typing import Any

from .base import Agent


class Librarian(Agent):
    ROLE = "librarian"
    OUTPUT_SCHEMA = {
        "research_question": "str",
        "background": "str",
        "known_vs_open": "list",
        "hypotheses": "list",
        "sources": "list",
    }

    def build_user_prompt(self, context: dict[str, Any]) -> str:
        seed = context.get("seed", {})
        seed_block = f"\nResearcher-provided seed (refine, don't discard):\n{seed}\n" if seed else ""
        return (
            "Frame the following into a researchable applied-social-research "
            "question and an evidence brief.\n\n"
            f"Topic / question from researcher:\n{context.get('question', '')}\n"
            f"{seed_block}"
            f"\nProgram framework: {context.get('framework', 'kirkpatrick')}\n\n"
            "Return JSON with keys: research_question, background, known_vs_open "
            "(list), hypotheses (list), sources (list of {claim, citation})."
        )
