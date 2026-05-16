"""Schema + storage round-trip tests. No external deps."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from codebook_builder import storage
from codebook_builder.storage import Variable


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.close()
    os.environ["CODEBOOK_DB_PATH"] = tmp.name
    conn = storage.connect()
    storage.run_migrations(conn)
    return conn, Path(tmp.name)


def test_migrations_apply_once():
    conn, _ = _fresh_db()
    applied = storage.applied_migrations(conn)
    assert "0001_init" in applied
    assert "0002_views" in applied
    # Idempotent
    applied_now = storage.run_migrations(conn)
    assert applied_now == []


def test_insert_and_read_modern_helper():
    conn, _ = _fresh_db()
    with storage.transaction(conn):
        storage.upsert_survey(conn, survey_id="sv_test", qualtrics_id="SV_TEST", title="Test Survey")
        storage.upsert_instrument(conn, instrument_id="sv_test__default", survey_id="sv_test", name="Test", role="post")
        run_id = storage.start_run(
            conn, survey_id="sv_test", source="qualtrics", source_uri="SV_TEST",
            parser_version="t", claude_model=None, triggered_by="test",
        )
        storage.insert_variables(
            conn, run_id=run_id, survey_id="sv_test", instrument_id="sv_test__default",
            variables=[
                Variable(
                    variable_name="q1",
                    label="How satisfied are you?",
                    question_text="How satisfied are you?",
                    variable_type="Likert",
                    domain="Quality Rating",
                    dimension=None,
                    scale="5-point Likert: Very dissatisfied → Very satisfied",
                    response_options=[
                        (1.0, "Very dissatisfied"),
                        (2.0, "Dissatisfied"),
                        (3.0, "Neutral"),
                        (4.0, "Satisfied"),
                        (5.0, "Very satisfied"),
                    ],
                    position=0,
                )
            ],
        )
        storage.finish_run(conn, run_id=run_id, status="complete", n_variables=1)

    rows = storage.latest_helper_rows(conn, "sv_test", legacy=False)
    assert len(rows) == 5  # one row per response option
    first = rows[0]
    assert first["SurveyID"] == "sv_test"
    assert first["VariableName"] == "q1"
    assert first["Value_Numeric"] == 1.0
    assert first["Value_Text"] == "Very dissatisfied"
    assert first["VariableType"] == "Likert"


def test_versioning_returns_latest_run():
    conn, _ = _fresh_db()
    with storage.transaction(conn):
        storage.upsert_survey(conn, survey_id="sv_ver", title="Versioning Test")
        storage.upsert_instrument(conn, instrument_id="sv_ver__default", survey_id="sv_ver", name="x")
        old = storage.start_run(conn, survey_id="sv_ver", source="qualtrics", source_uri="x",
                                parser_version="t", claude_model=None, triggered_by="test")
        storage.insert_variables(
            conn, run_id=old, survey_id="sv_ver", instrument_id="sv_ver__default",
            variables=[Variable(variable_name="q_old", label="old label",
                                response_options=[(1.0, "Yes")])],
        )
        storage.finish_run(conn, run_id=old, status="complete", n_variables=1)

        new = storage.start_run(conn, survey_id="sv_ver", source="qualtrics", source_uri="x",
                                parser_version="t", claude_model=None, triggered_by="test")
        storage.insert_variables(
            conn, run_id=new, survey_id="sv_ver", instrument_id="sv_ver__default",
            variables=[Variable(variable_name="q_new", label="new label",
                                response_options=[(1.0, "Yes")])],
        )
        storage.finish_run(conn, run_id=new, status="complete", n_variables=1)

    rows = storage.latest_helper_rows(conn, "sv_ver", legacy=False)
    assert {r["VariableName"] for r in rows} == {"q_new"}, "v_helper_modern must return only the latest run"
