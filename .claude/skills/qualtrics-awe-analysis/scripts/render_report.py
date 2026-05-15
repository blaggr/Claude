#!/usr/bin/env python3
"""Render the AWE dashboard HTML from a processed summary.json."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    HAS_JINJA = True
except ImportError:
    HAS_JINJA = False
    import string

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = SCRIPT_DIR.parent / "templates"

DIM_COLORS = {
    "L1_quality_process": "#0F3D5C",
    "L2_immediate_outcomes": "#2E8B8B",
    "L3_transfer_of_learning": "#E8A33D",
    "L4_long_term_outcomes": "#A33D3D",
}


def consolidate_questions(surveys: list[dict]) -> dict:
    """Group questions across surveys by dimension. Tags each with its role for display."""
    by_dim: dict[str, list[dict]] = {}
    for s in surveys:
        role = s["role"]
        for q in s.get("questions", []):
            dim = q.get("dimension")
            if not dim:
                continue
            qcopy = dict(q)
            qcopy["role"] = role
            by_dim.setdefault(dim, []).append(qcopy)
    return by_dim


def build_dimension_views(summary: dict) -> list[dict]:
    surveys = summary["surveys"]
    keywords = {}
    # Reconstruct dim metadata from the first survey's dimensions block
    for s in surveys:
        for k, v in s.get("dimensions", {}).items():
            keywords.setdefault(k, {"label": v["label"], "level": v["level"], "description": v["description"]})

    grouped = consolidate_questions(surveys)
    ordered = ["L1_quality_process", "L2_immediate_outcomes", "L3_transfer_of_learning", "L4_long_term_outcomes"]
    out = []
    for key in ordered:
        meta = keywords.get(key, {"label": key, "level": "?", "description": ""})
        items = grouped.get(key, [])
        likerts = [q for q in items if q.get("kind") == "likert" and q.get("mean") is not None]
        texts = [q for q in items if q.get("kind") == "text" and q.get("top_keywords")]

        # Sort likert items: post role first, then by mean desc
        role_order = {"post": 0, "pre": 1, "followup": 2}
        likerts_sorted = sorted(likerts, key=lambda q: (role_order.get(q.get("role"), 9), -q.get("mean", 0)))

        # Top items to display in table — prefer post-role for cleanliness if both exist
        questions_top = likerts_sorted[:8] if likerts_sorted else items[:5]

        chart_data = None
        if likerts_sorted:
            top = likerts_sorted[:6]
            chart_data = {
                "labels": [truncate(q["text"], 50) + (f"  ({q['role']})" if q.get("role") else "") for q in top],
                "data": [q["mean"] for q in top],
                "max": max((q.get("scale_max") or 5) for q in top),
                "color": DIM_COLORS.get(key, "#0F3D5C"),
            }

        out.append({
            "key": key,
            "label": meta["label"],
            "level": meta["level"],
            "description": meta["description"],
            "question_count": len(items),
            "questions_top": questions_top,
            "text_themes": texts,
            "chart_data": chart_data,
        })
    return out


def truncate(s: str, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"


def build_kpis(summary: dict) -> list[dict]:
    surveys = summary["surveys"]
    kpis = []
    for s in surveys:
        kpis.append({
            "label": f"{s['role'].title()} responses",
            "value": s["n_responses"],
            "sub": truncate(s["name"], 32),
        })
    pairs = summary.get("pre_post_pairs", [])
    if pairs:
        gains = [p["delta"] for p in pairs if p["delta"] > 0]
        kpis.append({
            "label": "Pre→Post items improved",
            "value": f"{len(gains)} / {len(pairs)}",
            "sub": f"avg Δ = {round(sum(p['delta'] for p in pairs) / len(pairs), 2)}",
        })
    # Per-dimension averages
    grouped = consolidate_questions(surveys)
    for key in ["L1_quality_process", "L2_immediate_outcomes", "L3_transfer_of_learning", "L4_long_term_outcomes"]:
        items = [q for q in grouped.get(key, []) if q.get("kind") == "likert" and q.get("mean") is not None and q.get("role") in (None, "post", "followup")]
        if not items:
            continue
        avg = round(sum(q["mean"] for q in items) / len(items), 2)
        scale = items[0].get("scale_max") or 5
        kpis.append({
            "label": key.split("_", 1)[1].replace("_", " ").title(),
            "value": f"{avg} / {scale}",
            "sub": f"{len(items)} item{'s' if len(items) != 1 else ''}",
        })
    return kpis


def build_pre_post_chart(summary: dict):
    pairs = summary.get("pre_post_pairs", [])
    if not pairs:
        return None
    top = pairs[:8]
    return {
        "labels": [truncate(p["text"], 50) for p in top],
        "pre":  [p["pre_mean"] for p in top],
        "post": [p["post_mean"] for p in top],
        "max":  max((p.get("scale_max") or 5) for p in top),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", required=True, help="Directory with summary.json")
    ap.add_argument("--out", required=True, help="Output HTML path")
    ap.add_argument("--title", default="Academy for Workforce Excellence — Training Evaluation")
    args = ap.parse_args()

    summary = json.loads((Path(args.processed) / "summary.json").read_text())

    surveys = summary["surveys"]
    survey_summary = " · ".join(f"{s['role']}: {s['name']} (n={s['n_responses']})" for s in surveys)

    dimensions = build_dimension_views(summary)
    kpis = build_kpis(summary)
    pre_post_chart = build_pre_post_chart(summary)

    chart_data = {
        "pre_post": pre_post_chart,
        "dimensions": {d["key"]: d["chart_data"] for d in dimensions if d["chart_data"]},
    }

    context = {
        "title": args.title,
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "survey_summary": survey_summary,
        "kpis": kpis,
        "dimensions": dimensions,
        "pre_post_pairs": summary.get("pre_post_pairs", []),
        "chart_data_json": json.dumps(chart_data),
    }

    if not HAS_JINJA:
        # Minimal fallback: render without filter support is hard; require jinja2.
        import sys
        sys.exit("jinja2 is required: pip install jinja2")

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=select_autoescape(["html"]))
    template = env.get_template("dashboard.html.j2")
    html = template.render(**context)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"[render] wrote {out_path}", flush=True)


if __name__ == "__main__":
    main()
