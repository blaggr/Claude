"""Normalizer tests — rule-based path only (no network)."""
from __future__ import annotations

import os

# Force the rule-based fallback even if a key is sitting in the env
os.environ.pop("ANTHROPIC_API_KEY", None)

from codebook_builder import normalize  # noqa: E402


def test_qualtrics_multiple_choice_becomes_variable():
    qs = [
        {
            "qid": "QID1",
            "export_tag": "Q1_satisfaction",
            "stem": "How satisfied are you?",
            "type": "MC",
            "selector": "SAVR",
            "choices": [
                {"value": 1, "text": "Very dissatisfied"},
                {"value": 5, "text": "Very satisfied"},
            ],
            "block": "Block 1",
            "position": 0,
        }
    ]
    vars_ = normalize.normalize_qualtrics_questions(qs, use_llm=False)
    assert len(vars_) == 1
    v = vars_[0]
    assert v.variable_name == "Q1_satisfaction"
    assert v.variable_type == "Multiple Choice"
    assert v.label.startswith("How satisfied")
    assert v.flag == "Needs Rob Review"  # rule-based path defers to a human
    assert len(v.response_options) == 2


def test_matrix_emits_one_variable_per_row():
    qs = [
        {
            "qid": "QID2",
            "sub_qid": "1",
            "export_tag": "Q2_1",
            "stem": "How important are the following?",
            "sub_stem": "Climbing structures",
            "type": "Matrix",
            "selector": "Likert",
            "choices": [
                {"value": 1, "text": "Not important"},
                {"value": 4, "text": "Very important"},
            ],
            "block": "Backyard needs",
            "position": 0,
        },
        {
            "qid": "QID2",
            "sub_qid": "2",
            "export_tag": "Q2_2",
            "stem": "How important are the following?",
            "sub_stem": "Garden area",
            "type": "Matrix",
            "selector": "Likert",
            "choices": [
                {"value": 1, "text": "Not important"},
                {"value": 4, "text": "Very important"},
            ],
            "block": "Backyard needs",
            "position": 1,
        },
    ]
    vars_ = normalize.normalize_qualtrics_questions(qs, use_llm=False)
    assert len(vars_) == 2
    assert vars_[0].variable_type == "Likert"
    assert "Climbing structures" in (vars_[0].label or "")
    assert "Garden area" in (vars_[1].label or "")
