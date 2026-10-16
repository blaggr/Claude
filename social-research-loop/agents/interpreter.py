"""Interpreter — Stage 5 (Interpret): map results onto the framework."""
from __future__ import annotations

from typing import Any

from .base import Agent


# Level definitions per supported framework. The responsible-AI lens is applied
# on top of whichever framework is chosen.
FRAMEWORK_LEVELS = {
    "kirkpatrick": "reaction, learning, behavior/transfer, results",
    "reaim": "reach, effectiveness, adoption, implementation, maintenance",
    "cfir": "intervention characteristics, outer setting, inner setting, individuals, process",
    "responsible_ai": "fairness/disparate impact, transparency, accountability, human oversight, validity-in-context",
}


class Interpreter(Agent):
    ROLE = "interpreter"
    OUTPUT_SCHEMA = {
        "framework": "str",
        "findings_by_level": "dict",
        "equity_findings": "dict",
        "confidence": "dict",
        "signal_vs_noise": "str",
    }

    def build_user_prompt(self, context: dict[str, Any]) -> str:
        framework = context.get("framework", "kirkpatrick")
        levels = FRAMEWORK_LEVELS.get(framework, "the framework's levels")
        ra_levels = FRAMEWORK_LEVELS["responsible_ai"]
        return (
            f"Map the analysis onto the {framework} framework "
            f"({levels}). For each level state the finding, the supporting "
            "evidence, and a confidence level. Separate genuine signal from "
            "noise; do not over-reach beyond what the data supports.\n\n"
            "Then ALSO apply the responsible-AI lens "
            f"({ra_levels}) using the disparate-impact analysis: report whether "
            "outcomes differ across the served subgroups, and never infer one "
            "subgroup's outcome from another's.\n\n"
            f"Analysis (incl. disparate-impact results): {context.get('analyze', {})}\n\n"
            "Return JSON with keys: framework, findings_by_level "
            "(level -> {finding, evidence, confidence}), equity_findings "
            "(subgroup -> {finding, evidence, confidence}), confidence, "
            "signal_vs_noise."
        )
