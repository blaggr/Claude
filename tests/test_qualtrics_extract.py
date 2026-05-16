"""Qualtrics definition → question dict extraction."""
from __future__ import annotations

from codebook_builder.sources import qualtrics as qsrc


SAMPLE_DEF = {
    "Flow": [{"ID": "BL_1"}],
    "Blocks": {
        "BL_1": {
            "Description": "Satisfaction Block",
            "BlockElements": [
                {"Type": "Question", "QuestionID": "QID1"},
                {"Type": "Question", "QuestionID": "QID2"},
                {"Type": "PageBreak"},
            ],
        }
    },
    "Questions": {
        "QID1": {
            "QuestionType": "MC",
            "Selector": "SAVR",
            "DataExportTag": "satisfaction",
            "QuestionText": "How satisfied are you?",
            "Choices": {
                "1": {"Display": "Very dissatisfied"},
                "5": {"Display": "Very satisfied"},
            },
        },
        "QID2": {
            "QuestionType": "Matrix",
            "Selector": "Likert",
            "DataExportTag": "needs",
            "QuestionText": "How important are the following?",
            "Choices": {
                "row_a": {"Display": "Climbing structures"},
                "row_b": {"Display": "Garden area"},
            },
            "Answers": {
                "1": {"Display": "Not important"},
                "4": {"Display": "Very important"},
            },
        },
    },
}


def test_extract_multiple_choice_and_matrix():
    out = qsrc.extract_questions(SAMPLE_DEF)
    assert len(out) == 3  # 1 MC + 2 matrix rows

    mc = next(q for q in out if q["type"] == "MC")
    assert mc["export_tag"] == "satisfaction"
    assert mc["block"] == "Satisfaction Block"
    assert {c["text"] for c in mc["choices"]} == {"Very dissatisfied", "Very satisfied"}

    matrix_rows = [q for q in out if q["type"] == "Matrix"]
    assert len(matrix_rows) == 2
    row_texts = {r["sub_stem"] for r in matrix_rows}
    assert row_texts == {"Climbing structures", "Garden area"}
    # Matrix answers come from the "Answers" map, not "Choices"
    assert all(len(r["choices"]) == 2 for r in matrix_rows)
    assert all({c["text"] for c in r["choices"]} == {"Not important", "Very important"} for r in matrix_rows)
