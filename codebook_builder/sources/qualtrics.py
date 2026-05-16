"""Qualtrics ingestion source.

Reuses the existing `pull_qualtrics.py` skill module (resolve_survey,
fetch_definition) — we do not duplicate the API client or retry logic.
Outputs a normalized list of question dicts ready for the LLM normalizer.

Question dict shape::

    {
        "qid": "QID12",                # Qualtrics's internal question id
        "export_tag": "Q5",            # the tag analysts see in the CSV
        "stem": "How satisfied...",
        "type": "MC|Matrix|TE|...",    # Qualtrics QuestionType
        "selector": "SAVR|MAVR|...",   # Qualtrics Selector (sub-type)
        "choices": [{"value": 1, "text": "Strongly disagree"}, ...],
        "sub_questions": [...],        # for Matrix questions
        "block": "Block 1",
        "position": 7
    }
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PULL = REPO_ROOT / ".claude" / "skills" / "qualtrics-awe-analysis" / "scripts" / "pull_qualtrics.py"


def _load_skill_module() -> Any:
    spec = importlib.util.spec_from_file_location("qualtrics_pull_skill", SKILL_PULL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Qualtrics pull skill at {SKILL_PULL}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["qualtrics_pull_skill"] = mod
    spec.loader.exec_module(mod)
    return mod


def resolve_and_fetch(survey_arg: str) -> tuple[str, str, dict]:
    """Resolve a survey ID or title, then fetch its full definition.

    Returns (survey_id, name, definition).
    """
    skill = _load_skill_module()
    survey_id, name = skill.resolve_survey(survey_arg)
    definition = skill.fetch_definition(survey_id)
    return survey_id, name, definition


def extract_questions(definition: dict) -> list[dict]:
    """Flatten a Qualtrics survey-definitions payload into a list of question dicts.

    Handles:
      * Multiple Choice (single / multi)
      * Text Entry
      * Matrix (one virtual question per sub-question row)
      * Slider / Numeric / Date / Constant Sum (best-effort)

    Skips display-only blocks (PageBreak, etc.).
    """
    questions: list[dict] = []
    flow = definition.get("Flow") or []
    blocks = definition.get("Blocks") or {}
    raw_questions = definition.get("Questions") or {}

    # Build qid -> block-name index by walking the flow
    block_of: dict[str, str] = {}
    block_position: dict[str, int] = {}
    pos = 0
    for block_entry in flow:
        block_id = block_entry.get("ID")
        block_meta = blocks.get(block_id, {})
        block_name = block_meta.get("Description") or block_meta.get("BlockType") or block_id or "Block"
        for elem in (block_meta.get("BlockElements") or []):
            if elem.get("Type") == "Question":
                qid = elem.get("QuestionID")
                if qid:
                    block_of[qid] = block_name
                    block_position[qid] = pos
                    pos += 1

    for qid, q in raw_questions.items():
        qtype = q.get("QuestionType")
        if qtype in {"DB", "Timing", "Meta"}:  # non-data
            continue
        export_tag = q.get("DataExportTag") or qid
        stem = (q.get("QuestionText") or "").strip()
        selector = q.get("Selector")
        block = block_of.get(qid, "")
        position = block_position.get(qid, 10_000)

        choices = _choices(q)

        # Matrix questions: emit one variable per row (sub-question)
        if qtype == "Matrix":
            for sub_qid, sub_meta in (q.get("Choices") or {}).items():
                # In Matrix, "Choices" are the row stems, "Answers" are the scale points
                row_text = sub_meta.get("Display") or sub_meta.get("ChoiceText") or sub_qid
                answers = [
                    {"value": _coerce_value(k), "text": (v.get("Display") or v.get("ChoiceText") or "").strip()}
                    for k, v in (q.get("Answers") or {}).items()
                ]
                questions.append({
                    "qid": qid,
                    "sub_qid": sub_qid,
                    "export_tag": f"{export_tag}_{sub_qid}",
                    "stem": stem,
                    "sub_stem": row_text,
                    "type": qtype,
                    "selector": selector,
                    "choices": answers,
                    "block": block,
                    "position": position,
                })
            continue

        questions.append({
            "qid": qid,
            "export_tag": export_tag,
            "stem": stem,
            "type": qtype,
            "selector": selector,
            "choices": choices,
            "block": block,
            "position": position,
        })

    questions.sort(key=lambda x: x["position"])
    return questions


def _choices(q: dict) -> list[dict]:
    out = []
    for k, v in (q.get("Choices") or {}).items():
        text = (v.get("Display") or v.get("ChoiceText") or "").strip()
        out.append({"value": _coerce_value(k), "text": text})
    return out


def _coerce_value(raw: Any) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None
