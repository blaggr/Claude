"""Claude-based question → Variable normalizer.

Takes raw question dicts (from sources/qualtrics.py) or a free-text dump (from
sources/document.py) and returns canonical :class:`storage.Variable` rows that
match the AWE Notion Variables schema.

The normalizer uses Claude (claude-opus-4-7 by default) with structured JSON
output. The system prompt + few-shot examples are cached so cost stays low even
when ingesting many surveys.

Two pathways:
    normalize_qualtrics_questions(questions, ...) -> list[Variable]
    normalize_document_text(text, ...)             -> list[Variable]

Both flow through ``_call_claude``. When ``ANTHROPIC_API_KEY`` is unset, the
normalizer falls back to a deterministic rule-based path so the rest of the
pipeline (storage, API, Streamlit) still works in dev / test environments. The
rule-based path covers Qualtrics ingest reasonably well; the document path
returns empty in that mode (we'd be guessing).
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Sequence

from .storage import Variable

DEFAULT_MODEL = "claude-opus-4-7"
PARSER_VERSION = "0.1.0"

DOMAINS = [
    "Quality Rating", "Knowledge", "Climate", "Engagement",
    "Self-Efficacy", "Attitudes", "Behavioral Intention",
    "Demographic", "Trainer Feedback", "Other",
]
VARIABLE_TYPES = [
    "Likert", "Multiple Choice", "Free Text", "Numeric",
    "Date", "Composite", "Derived", "Demographic", "Unknown",
]

SYSTEM_PROMPT = """You convert messy survey question metadata into canonical \
codebook rows for the AVA Lab's "Internal Helper Columns" schema.

For each input question, produce exactly one row in the output JSON array with \
these keys (use null for unknown):
- variable_name:   short canonical id (snake_case). Prefer the source's export \
tag when present; otherwise derive from the stem.
- label:           the full item text as presented to a respondent (verbatim).
- question_text:   the prompt only (without sub-question or bracketed row text).
- variable_type:   one of [Likert, Multiple Choice, Free Text, Numeric, Date, \
Composite, Derived, Demographic, Unknown]
- domain:          comma-separated subset of [Quality Rating, Knowledge, \
Climate, Engagement, Self-Efficacy, Attitudes, Behavioral Intention, \
Demographic, Trainer Feedback, Other]. Use Other if nothing fits.
- dimension:       finer-grained sub-domain when obvious (e.g. \
"Group Cohesion", "Trainer Knowledge"). Null if not.
- scale:           short description of the response scale (e.g. \
"5-point Likert: Strongly disagree → Strongly agree").
- reverse_scored:  true only if the item wording is plainly reverse-coded \
(e.g. "I do NOT feel...").
- derivation_logic: null for raw items.
- response_options: array of {value_numeric, value_text} preserving order.

Rules:
- Do NOT invent items. One input → one output.
- Use null instead of empty strings.
- Flag = "Needs Rob Review" if the question_type or domain is ambiguous; \
otherwise null."""


def normalize_qualtrics_questions(
    questions: Sequence[dict],
    *,
    model: str = DEFAULT_MODEL,
    use_llm: bool | None = None,
) -> list[Variable]:
    """Convert Qualtrics question dicts into Variables.

    If ``use_llm`` is None we auto-detect: LLM if ``ANTHROPIC_API_KEY`` is set,
    otherwise rule-based fallback.
    """
    if use_llm is None:
        use_llm = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if not use_llm:
        return [_rule_based_variable(q, position=i) for i, q in enumerate(questions)]

    payload = _call_claude(_qualtrics_user_prompt(questions), model=model)
    rows = payload.get("variables", []) if isinstance(payload, dict) else payload
    return [_variable_from_json(r, fallback_position=i) for i, r in enumerate(rows)]


def normalize_document_text(
    text: str,
    *,
    model: str = DEFAULT_MODEL,
) -> list[Variable]:
    """Extract Variables from an unstructured PDF/DOCX text payload."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        # No safe heuristic for free-text surveys; surface the limitation.
        raise RuntimeError(
            "Document ingestion requires ANTHROPIC_API_KEY to call Claude. "
            "Set the env var, or ingest via Qualtrics instead."
        )

    user = (
        "Extract every survey question from the following document text. "
        "Return a JSON object {\"variables\": [...]} where each item conforms "
        "to the schema in your system prompt.\n\n"
        f"<document>\n{text}\n</document>"
    )
    payload = _call_claude(user, model=model)
    rows = payload.get("variables", []) if isinstance(payload, dict) else payload
    return [_variable_from_json(r, fallback_position=i) for i, r in enumerate(rows)]


# ----------------------------------------------------------- Claude integration


def _call_claude(user_prompt: str, *, model: str) -> Any:
    try:
        import anthropic  # type: ignore
    except ImportError as e:
        raise ImportError(
            "The `anthropic` SDK is required for LLM normalization. "
            "Run `pip install anthropic` and set ANTHROPIC_API_KEY."
        ) from e

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=8192,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
    return _parse_json_blob(text)


def _qualtrics_user_prompt(questions: Sequence[dict]) -> str:
    return (
        "Convert these Qualtrics questions into the canonical codebook schema. "
        "Return a single JSON object {\"variables\": [...]}.\n\n"
        f"<questions>\n{json.dumps(list(questions), indent=2)}\n</questions>"
    )


def _parse_json_blob(text: str) -> Any:
    text = text.strip()
    # Tolerate code fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


# ----------------------------------------------------------- rule-based fallback


def _rule_based_variable(q: dict, *, position: int) -> Variable:
    qtype = q.get("type")
    selector = q.get("selector")
    variable_type = _map_qualtrics_type(qtype, selector)

    stem = (q.get("stem") or "").strip()
    sub_stem = (q.get("sub_stem") or "").strip() if "sub_stem" in q else ""
    label = f"{stem} [{sub_stem}]" if sub_stem else stem
    label = _strip_html(label)

    options = [
        (c.get("value"), c.get("text") or "")
        for c in (q.get("choices") or [])
        if (c.get("text") or "").strip()
    ]
    scale = _summarize_scale(options) if options else None
    domain = "Other"  # safe default; LLM run would refine

    return Variable(
        variable_name=str(q.get("export_tag") or q.get("qid") or f"q_{position}"),
        label=label or None,
        question_text=_strip_html(stem) or None,
        variable_type=variable_type,
        domain=domain,
        dimension=None,
        scale=scale,
        reverse_scored=False,
        derivation_logic=None,
        source_instrument=q.get("block") or None,
        cours=None,
        notes=None,
        flag="Needs Rob Review",
        position=position,
        response_options=options,
    )


def _map_qualtrics_type(qtype: str | None, selector: str | None) -> str:
    if qtype == "MC":
        return "Multiple Choice"
    if qtype == "Matrix":
        # Matrix questions are almost always Likert-style in AWE work
        return "Likert"
    if qtype == "TE":
        return "Free Text"
    if qtype == "Slider":
        return "Numeric"
    if qtype == "DD":
        return "Multiple Choice"
    if qtype == "Date":
        return "Date"
    if qtype == "CS":  # Constant Sum
        return "Numeric"
    return "Unknown"


def _summarize_scale(options: list[tuple[float | None, str]]) -> str:
    texts = [t for _, t in options if t]
    if not texts:
        return ""
    if len(texts) <= 2:
        return " / ".join(texts)
    return f"{len(texts)}-point: {texts[0]} → {texts[-1]}"


_HTML_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return _HTML_RE.sub("", s).replace("&nbsp;", " ").strip()


# ----------------------------------------------------------- JSON → Variable


def _variable_from_json(row: dict, *, fallback_position: int) -> Variable:
    options_raw = row.get("response_options") or []
    options: list[tuple[float | None, str]] = []
    for o in options_raw:
        if isinstance(o, dict):
            val = o.get("value_numeric")
            try:
                val = float(val) if val is not None else None
            except (TypeError, ValueError):
                val = None
            options.append((val, str(o.get("value_text") or "")))
    return Variable(
        variable_name=str(row.get("variable_name") or f"q_{fallback_position}"),
        label=_nonempty(row.get("label")),
        question_text=_nonempty(row.get("question_text")),
        variable_type=_clamp(row.get("variable_type"), VARIABLE_TYPES, "Unknown"),
        domain=_clamp_multi(row.get("domain"), DOMAINS, "Other"),
        dimension=_nonempty(row.get("dimension")),
        scale=_nonempty(row.get("scale")),
        reverse_scored=bool(row.get("reverse_scored")),
        derivation_logic=_nonempty(row.get("derivation_logic")),
        source_instrument=_nonempty(row.get("source_instrument")),
        cours=_nonempty(row.get("cours")),
        notes=_nonempty(row.get("notes")),
        flag=_nonempty(row.get("flag")),
        position=row.get("position", fallback_position),
        response_options=options,
    )


def _nonempty(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _clamp(v: Any, allowed: list[str], default: str) -> str:
    if not v:
        return default
    s = str(v).strip()
    return s if s in allowed else default


def _clamp_multi(v: Any, allowed: list[str], default: str) -> str:
    if not v:
        return default
    parts = [p.strip() for p in str(v).split(",")]
    keep = [p for p in parts if p in allowed]
    return ", ".join(keep) if keep else default
