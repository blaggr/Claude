"""Analyst — Stage 4 (Analyze): statistics, tables, assumption checks.

Phase 2 wires this to a de-identified dataset (e.g. a Qualtrics export). The
Analyst computes results in code and uses the LLM to narrate/structure them —
never to invent numbers.
"""
from __future__ import annotations

from typing import Any

from .base import Agent


class Analyst(Agent):
    ROLE = "analyst"
    OUTPUT_SCHEMA = {
        "descriptives": "dict",
        "comparisons": "list",
        "disparate_impact": "dict",
        "reliability": "dict",
        "assumptions": "list",
        "tables": "list",
        "caveats": "list",
    }

    def build_user_prompt(self, context: dict[str, Any]) -> str:
        design = context.get("design", {})
        return (
            "Analyze the prepared de-identified results per the analysis plan. "
            "Report descriptives, group comparisons with effect sizes, scale "
            "reliability, and explicitly state and check assumptions. Do NOT "
            "fabricate values — only structure/interpret the numbers provided.\n\n"
            "Also run the pre-specified DISPARATE-IMPACT analysis: for each "
            "served subgroup, report the relevant outcome/error rates and "
            "between-group differences (with uncertainty), and flag any subgroup "
            "with too few cases to assess rather than glossing over it.\n\n"
            f"Analysis plan: {design.get('analysis_plan', '')}\n"
            f"Computed results (from data layer): {context.get('computed_results', '{}')}\n\n"
            "Return JSON with keys: descriptives, comparisons (list of "
            "{contrast, stat, effect_size, p}), disparate_impact "
            "(subgroup -> {metric, value, difference_vs_reference, n, note}), "
            "reliability, assumptions (list of {assumption, met, note}), tables, "
            "caveats."
        )
