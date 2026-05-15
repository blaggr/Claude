#!/usr/bin/env python3
"""Classify Qualtrics survey questions into Kirkpatrick dimensions, join pre/post/followup
by participant ID, and emit summary stats.

Reads CSVs + definition JSONs from --raw, writes summary.json + tables to --out.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
KEYWORDS_PATH = SCRIPT_DIR.parent / "reference" / "kirkpatrick_keywords.json"

JOIN_CANDIDATES = [
    "ParticipantID", "Participant_ID", "participantId", "participantid",
    "EmployeeID", "Employee_ID", "EmployeeId", "employeeid",
    "Q_EmployeeID", "Q_ParticipantID",
    "EmpID", "Emp_ID",
]

STOPWORDS = {
    "the","a","an","and","or","but","of","to","in","on","at","for","with","by",
    "is","are","was","were","be","been","being","i","you","we","they","he","she","it",
    "this","that","these","those","my","your","our","their","his","her","its",
    "do","does","did","have","has","had","not","no","yes","so","than","then",
    "as","if","very","much","more","most","some","any","all","each","every","just",
    "can","could","would","should","will","may","might","also",
    "after","before","during","since","because","while","when","where","what","which","who","how",
    "training","course","module","program","session","awe","academy",
}

PRE_POST_STRIP = [
    r"^before (the |this )?(training|course|module|program|session)[,:]?\s*",
    r"^after (the |this )?(training|course|module|program|session)[,:]?\s*",
    r"^prior to (the |this )?(training|course|module|program|session)[,:]?\s*",
    r"^now that you have completed[^,]*[,:]?\s*",
    r"^thinking back to (the |this )?(training|course|module|program|session)[,:]?\s*",
    r"^as a result of[^,]*[,:]?\s*",
]


def load_keywords() -> dict:
    return json.loads(KEYWORDS_PATH.read_text())


def extract_questions(definition: dict) -> dict:
    """Return {questionId: {text, choices: [labels], type, dataExportTag}} from a survey definition."""
    out = {}
    qs = definition.get("Questions") or definition.get("questions") or {}
    if isinstance(qs, list):
        # Some endpoints return a list
        qs = {q.get("QuestionID") or q.get("id"): q for q in qs if (q.get("QuestionID") or q.get("id"))}

    for qid, q in qs.items():
        text = (
            q.get("QuestionText")
            or q.get("questionText")
            or q.get("QuestionText_Unsafe")
            or ""
        )
        # Strip HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        tag = q.get("DataExportTag") or q.get("dataExportTag") or qid

        choices = q.get("Choices") or q.get("choices") or {}
        choice_labels = []
        if isinstance(choices, dict):
            # Qualtrics keys choices by index
            for k in sorted(choices.keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
                c = choices[k]
                if isinstance(c, dict):
                    choice_labels.append(c.get("Display") or c.get("display") or "")
        elif isinstance(choices, list):
            for c in choices:
                if isinstance(c, dict):
                    choice_labels.append(c.get("Display") or c.get("display") or "")

        qtype = (q.get("QuestionType") or q.get("questionType") or "").upper()
        selector = (q.get("Selector") or q.get("selector") or "").upper()

        out[qid] = {
            "id": qid,
            "text": text,
            "tag": tag,
            "type": qtype,
            "selector": selector,
            "choices": [c for c in choice_labels if c],
        }
    return out


def classify(text: str, keywords: dict) -> str | None:
    """Return the dimension key (e.g. 'L2_immediate_outcomes') or None if no match."""
    if not text:
        return None
    t = text.lower()
    for dim_key in keywords["_priority_order"]:
        spec = keywords[dim_key]
        for kw in spec["keywords"]:
            if kw.lower() in t:
                return dim_key
        for pat in spec.get("regex", []):
            if re.search(pat, t, re.IGNORECASE):
                return dim_key
    return None


def normalize_stem(text: str) -> str:
    t = text.lower().strip()
    for pat in PRE_POST_STRIP:
        t = re.sub(pat, "", t, flags=re.IGNORECASE)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:80]


def likert_scale(choices: list[str]) -> dict | None:
    """If choices look like a Likert scale, return mapping label -> numeric value."""
    if not choices or len(choices) < 3 or len(choices) > 11:
        return None
    canon = [c.strip().lower() for c in choices]
    agree_pat = ["strongly disagree", "disagree", "neutral", "neither", "agree", "strongly agree"]
    if any("strongly agree" in c for c in canon) or any("strongly disagree" in c for c in canon):
        return _scale_from_anchors(choices)
    quality_pat = ["poor", "fair", "good", "very good", "excellent"]
    if any(p in canon for p in quality_pat) and len([c for c in canon if c in quality_pat]) >= 3:
        return _scale_from_anchors(choices)
    confidence_pat = ["not confident", "slightly confident", "somewhat confident", "confident", "very confident", "extremely confident"]
    if any("confident" in c for c in canon) and len(choices) <= 7:
        return _scale_from_anchors(choices)
    frequency_pat = ["never", "rarely", "sometimes", "often", "always", "daily", "weekly"]
    if any(p in canon for p in frequency_pat) and len([c for c in canon if c in frequency_pat]) >= 3:
        return _scale_from_anchors(choices)
    if any("satisfied" in c or "dissatisfied" in c for c in canon) and len(choices) <= 7:
        return _scale_from_anchors(choices)
    likely_pat = ["not at all likely", "slightly likely", "moderately likely", "very likely", "extremely likely"]
    if any("likely" in c for c in canon) and len(choices) <= 7:
        return _scale_from_anchors(choices)
    # Numeric scale like "1", "2", "3", "4", "5"
    if all(re.fullmatch(r"\s*\d+\s*", c) for c in choices):
        return {c: int(c.strip()) for c in choices}
    return None


def _scale_from_anchors(choices: list[str]) -> dict:
    return {c: i + 1 for i, c in enumerate(choices)}


def read_csv_responses(path: Path) -> tuple[list[str], list[dict]]:
    """Qualtrics CSV export has 3 header rows: header, question text, JSON metadata. Return (column names, rows)."""
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if len(rows) < 4:
        return [], []
    headers = rows[0]
    # rows[1] is full question text, rows[2] is JSON metadata. Data starts at row 3.
    data_rows = [dict(zip(headers, r)) for r in rows[3:]]
    return headers, data_rows


def find_join_column(headers: list[str], preferred: str) -> str | None:
    if preferred in headers:
        return preferred
    for cand in [preferred, *JOIN_CANDIDATES]:
        if cand in headers:
            return cand
    # Try case-insensitive match
    lowered = {h.lower(): h for h in headers}
    for cand in [preferred, *JOIN_CANDIDATES]:
        if cand.lower() in lowered:
            return lowered[cand.lower()]
    return None


def question_id_for_column(col: str, questions: dict) -> str | None:
    """Map CSV column (e.g. 'Q5' or DataExportTag) back to a definition question ID."""
    if col in questions:
        return col
    for qid, q in questions.items():
        if q["tag"] == col or qid == col:
            return qid
    # Qualtrics suffix forms: Q5_1, Q5_TEXT
    base = col.split("_")[0]
    if base in questions:
        return base
    for qid, q in questions.items():
        if q["tag"] == base:
            return qid
    return None


def stats_for_question(rows: list[dict], col: str, q: dict) -> dict:
    values = [r.get(col, "").strip() for r in rows if r.get(col, "").strip()]
    n = len(values)
    out = {"id": q["id"], "tag": q["tag"], "text": q["text"], "n": n}

    scale = likert_scale(q["choices"]) if q.get("choices") else None
    if scale:
        numeric = [scale[v] for v in values if v in scale]
        if numeric:
            out["scale_max"] = max(scale.values())
            out["mean"] = round(statistics.fmean(numeric), 2)
            out["stdev"] = round(statistics.pstdev(numeric), 2) if len(numeric) > 1 else 0.0
        out["distribution"] = dict(Counter(values))
        out["scale"] = scale
        out["kind"] = "likert"
        return out

    if q["choices"]:
        out["distribution"] = dict(Counter(values))
        out["kind"] = "categorical"
        return out

    # Treat as free text
    tokens = []
    for v in values:
        for tok in re.findall(r"[a-zA-Z']{3,}", v.lower()):
            if tok not in STOPWORDS:
                tokens.append(tok)
    out["top_keywords"] = Counter(tokens).most_common(10)
    out["sample_responses"] = values[:5]
    out["kind"] = "text"
    return out


def build_dimension_summary(question_stats: list[dict], keywords: dict) -> dict:
    by_dim = defaultdict(list)
    for qs in question_stats:
        dim = qs.get("dimension")
        if dim:
            by_dim[dim].append(qs)
    summary = {}
    for dim_key, spec in keywords.items():
        if dim_key.startswith("_"):
            continue
        items = by_dim.get(dim_key, [])
        likerts = [i for i in items if i.get("kind") == "likert" and "mean" in i]
        avg_mean = round(statistics.fmean([i["mean"] for i in likerts]), 2) if likerts else None
        summary[dim_key] = {
            "label": spec["label"],
            "level": spec["kirkpatrick_level"],
            "description": spec["description"],
            "question_count": len(items),
            "avg_likert_mean": avg_mean,
            "scale_max": likerts[0]["scale_max"] if likerts else None,
            "questions": items,
        }
    return summary


def match_pre_post(pre_stats: list[dict], post_stats: list[dict]) -> list[dict]:
    """Pair pre/post questions by normalized stem; report mean delta."""
    pre_by_stem = {normalize_stem(q["text"]): q for q in pre_stats if q.get("kind") == "likert" and "mean" in q}
    pairs = []
    for q in post_stats:
        if q.get("kind") != "likert" or "mean" not in q:
            continue
        stem = normalize_stem(q["text"])
        if stem and stem in pre_by_stem:
            pre = pre_by_stem[stem]
            if pre.get("scale_max") != q.get("scale_max"):
                continue
            pairs.append({
                "text": q["text"],
                "dimension": q.get("dimension"),
                "pre_mean": pre["mean"],
                "post_mean": q["mean"],
                "delta": round(q["mean"] - pre["mean"], 2),
                "n_pre": pre["n"],
                "n_post": q["n"],
                "scale_max": q.get("scale_max"),
            })
    return sorted(pairs, key=lambda p: p["delta"], reverse=True)


def analyze_survey(role: str, csv_path: Path, def_path: Path, join_key: str, keywords: dict) -> dict:
    definition_blob = json.loads(def_path.read_text())
    definition = definition_blob.get("definition", {})
    name = definition_blob.get("name", role)
    survey_id = definition_blob.get("surveyId", "")

    questions = extract_questions(definition)
    headers, rows = read_csv_responses(csv_path)

    join_col = find_join_column(headers, join_key)
    participant_ids = [r.get(join_col, "").strip() for r in rows] if join_col else []
    participant_ids = [p for p in participant_ids if p]

    # Per-column stats
    question_stats = []
    seen_qids = set()
    for col in headers:
        qid = question_id_for_column(col, questions)
        if not qid or qid in seen_qids:
            # For multi-part questions (matrix), still report each sub-column if it has data
            if qid and qid in questions and "_" in col:
                q = dict(questions[qid])
                # Tag sub-column variant
                sub_label = col
                q["text"] = f"{q['text']} [{sub_label}]"
                q["id"] = col
                stats = stats_for_question(rows, col, q)
                stats["dimension"] = classify(q["text"], keywords)
                question_stats.append(stats)
            continue
        seen_qids.add(qid)
        q = questions[qid]
        stats = stats_for_question(rows, col, q)
        stats["dimension"] = classify(q["text"], keywords)
        question_stats.append(stats)

    return {
        "role": role,
        "survey_id": survey_id,
        "name": name,
        "n_responses": len(rows),
        "join_column": join_col,
        "n_with_join_key": len(participant_ids),
        "questions": question_stats,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True, help="Directory with <role>_<id>.csv + .definition.json files")
    ap.add_argument("--join-key", default="ParticipantID")
    ap.add_argument("--out", required=True, help="Output directory for processed summary")
    args = ap.parse_args()

    raw_dir = Path(args.raw)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    keywords = load_keywords()

    surveys = []
    for def_path in sorted(raw_dir.glob("*.definition.json")):
        role = def_path.name.split("_", 1)[0]
        survey_id = def_path.name[len(role) + 1 : -len(".definition.json")]
        csv_path = raw_dir / f"{role}_{survey_id}.csv"
        if not csv_path.exists():
            print(f"[analyze] warning: no CSV for {def_path.name}", file=sys.stderr)
            continue
        surveys.append(analyze_survey(role, csv_path, def_path, args.join_key, keywords))

    if not surveys:
        sys.exit("[analyze] no surveys found in raw directory")

    # Per-survey dimension summaries
    for s in surveys:
        s["dimensions"] = build_dimension_summary(s["questions"], keywords)

    # Pre/post pairing across surveys
    pre = next((s for s in surveys if s["role"] == "pre"), None)
    post = next((s for s in surveys if s["role"] == "post"), None)
    followup = next((s for s in surveys if s["role"] == "followup"), None)

    pre_post_pairs = match_pre_post(pre["questions"], post["questions"]) if pre and post else []
    post_followup_pairs = match_pre_post(post["questions"], followup["questions"]) if post and followup else []

    summary = {
        "surveys": surveys,
        "pre_post_pairs": pre_post_pairs,
        "post_followup_pairs": post_followup_pairs,
        "keywords_source": str(KEYWORDS_PATH.name),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"[analyze] wrote {out_dir / 'summary.json'} ({len(surveys)} surveys)", flush=True)


if __name__ == "__main__":
    main()
