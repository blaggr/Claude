"""Interpreter — Stage 5 (Interpret): map results onto the framework."""
from __future__ import annotations

from typing import Any

from .base import Agent


class Interpreter(Agent):
    ROLE = "interpreter"
    OUTPUT_SCHEMA = {
        "framework": "str",
        "findings_by_level": "dict",
        "confidence": "dict",
        "signal_vs_noise": "str",
    }

    def build_user_prompt(self, context: dict[str, Any]) -> str:
        framework = context.get("framework", "kirkpatrick")
        levels = {
            "kirkpatrick": "reaction, learning, behavior/transfer, results",
        }.get(framework, "the framework's levels")
        return (
            f"Map the analysis onto the {framework} framework "
            f"({levels}). For each level state the finding, the supporting "
            "evidence, and a confidence level. Separate genuine signal from "
            "noise; do not over-reach beyond what the data supports.\n\n"
            f"Analysis: {context.get('analyze', {})}\n\n"
            "Return JSON with keys: framework, findings_by_level "
            "(level -> {finding, evidence, confidence}), confidence, "
            "signal_vs_noise."
        )
