"""FastAPI service for the AVA Lab codebook generator.

Run with::

    uvicorn api.main:app --host 0.0.0.0 --port 8787

Endpoints (all require X-API-Key unless CODEBOOK_DISABLE_AUTH=1):

    POST  /ingest                          - kick off an ingestion run
    GET   /runs/{run_id}                   - run status
    GET   /helper?survey_id=...&format=... - latest helper rows (modern layout)
    GET   /helper/legacy?survey_id=...     - legacy 6-column layout
    GET   /variables?survey_id=...         - filtered variable rows (JSON)
    GET   /surveys?q=...                   - typeahead by id / title

The service is the SOLE writer to codebook.sqlite. Alteryx and other readers
connect to the SQLite file via ODBC for direct read access.
"""
from __future__ import annotations

import csv
import io
import tempfile
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from codebook_builder import normalize, storage
from codebook_builder.normalize import PARSER_VERSION

from .auth import verify_api_key
from .schemas import IngestResponse, RunSummary, SurveySummary

app = FastAPI(
    title="AVA Lab Codebook API",
    version="0.1.0",
    description="Generate and serve survey helper files / codebooks for the AVA Lab.",
)


def _conn():
    conn = storage.connect()
    storage.run_migrations(conn)
    return conn


@app.get("/health")
def health() -> dict:
    conn = _conn()
    n_surveys = conn.execute("SELECT COUNT(*) AS n FROM surveys").fetchone()["n"]
    n_vars = conn.execute("SELECT COUNT(*) AS n FROM variables").fetchone()["n"]
    return {"status": "ok", "surveys": n_surveys, "variables": n_vars}


@app.post("/ingest", response_model=IngestResponse)
def ingest(
    source: str = Form(...),
    survey_id: str | None = Form(None),
    survey_title: str | None = Form(None),
    qualtrics_arg: str | None = Form(None),
    instrument_id: str | None = Form(None),
    role: str | None = Form("post"),
    push_to_notion: bool = Form(False),
    file: UploadFile | None = File(None),
    user=Depends(verify_api_key),
) -> IngestResponse:
    conn = _conn()
    triggered_by = user.get("user_email")

    if source == "qualtrics":
        if not qualtrics_arg:
            raise HTTPException(400, "qualtrics_arg is required when source=qualtrics")
        from codebook_builder.sources import qualtrics as qsrc
        try:
            sid, name, definition = qsrc.resolve_and_fetch(qualtrics_arg)
        except SystemExit as e:
            raise HTTPException(404, str(e)) from e
        questions = qsrc.extract_questions(definition)
        with storage.transaction(conn):
            storage.upsert_survey(conn, survey_id=sid, qualtrics_id=sid, title=name)
            iid = instrument_id or f"{sid}__default"
            storage.upsert_instrument(conn, instrument_id=iid, survey_id=sid, name=name, role=role)
            run_id = storage.start_run(
                conn,
                survey_id=sid,
                source="qualtrics",
                source_uri=sid,
                parser_version=PARSER_VERSION,
                claude_model=normalize.DEFAULT_MODEL,
                triggered_by=triggered_by,
            )
        return _finish_ingest(conn, run_id, sid, iid, lambda: normalize.normalize_qualtrics_questions(questions), push_to_notion)

    if source in {"pdf", "docx"}:
        if not survey_id:
            raise HTTPException(400, "survey_id is required for pdf/docx ingest")
        if file is None:
            raise HTTPException(400, "file upload is required for pdf/docx ingest")

        # Save to a temp path so the document parser can mmap it
        suffix = ".pdf" if source == "pdf" else ".docx"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
            fh.write(file.file.read())
            tmp_path = Path(fh.name)

        from codebook_builder.sources import document as docsrc
        text = docsrc.extract_text(tmp_path)
        with storage.transaction(conn):
            storage.upsert_survey(conn, survey_id=survey_id, title=survey_title or file.filename or survey_id)
            iid = instrument_id or f"{survey_id}__default"
            storage.upsert_instrument(conn, instrument_id=iid, survey_id=survey_id, name=survey_title or file.filename or survey_id, role=role)
            run_id = storage.start_run(
                conn,
                survey_id=survey_id,
                source=source,
                source_uri=str(tmp_path),
                parser_version=PARSER_VERSION,
                claude_model=normalize.DEFAULT_MODEL,
                triggered_by=triggered_by,
            )
        return _finish_ingest(conn, run_id, survey_id, iid, lambda: normalize.normalize_document_text(text), push_to_notion)

    raise HTTPException(400, f"Unsupported source: {source}")


def _finish_ingest(conn, run_id: int, survey_id: str, instrument_id: str, normalizer, push_to_notion: bool) -> IngestResponse:
    try:
        vars_ = normalizer()
        with storage.transaction(conn):
            n = storage.insert_variables(conn, run_id=run_id, survey_id=survey_id, instrument_id=instrument_id, variables=vars_)
            storage.finish_run(conn, run_id=run_id, status="complete", n_variables=n, notes=f"{n} variables")
        if push_to_notion:
            from codebook_builder import notion_sync
            notion_sync.sync_run(run_id, conn)
        return IngestResponse(run_id=run_id, survey_id=survey_id, status="complete")
    except Exception as e:
        with storage.transaction(conn):
            storage.finish_run(conn, run_id=run_id, status="failed", n_variables=0, notes=str(e)[:500])
        raise HTTPException(500, f"Ingestion failed: {e}") from e


@app.get("/runs/{run_id}", response_model=RunSummary)
def get_run(run_id: int, user=Depends(verify_api_key)) -> RunSummary:
    conn = _conn()
    row = storage.get_run(conn, run_id)
    if not row:
        raise HTTPException(404, f"No run with id={run_id}")
    return RunSummary(**row)


@app.get("/surveys", response_model=list[SurveySummary])
def list_surveys(q: str | None = Query(None), user=Depends(verify_api_key)) -> list[SurveySummary]:
    conn = _conn()
    return [SurveySummary(**r) for r in storage.list_surveys(conn, q=q)]


@app.get("/helper")
def helper(
    survey_id: str = Query(...),
    format: str = Query("json", pattern="^(json|csv)$"),
    user=Depends(verify_api_key),
) -> Any:
    conn = _conn()
    rows = storage.latest_helper_rows(conn, survey_id, legacy=False)
    if not rows:
        raise HTTPException(404, f"No helper rows for survey {survey_id}")
    return _format_rows(rows, format, survey_id)


@app.get("/helper/legacy")
def helper_legacy(
    survey_id: str = Query(...),
    format: str = Query("json", pattern="^(json|csv)$"),
    user=Depends(verify_api_key),
) -> Any:
    conn = _conn()
    rows = storage.latest_helper_rows(conn, survey_id, legacy=True)
    if not rows:
        raise HTTPException(404, f"No legacy helper rows for survey {survey_id}")
    return _format_rows(rows, format, survey_id + "-legacy")


@app.get("/variables")
def variables(
    survey_id: str = Query(...),
    domain: str | None = Query(None),
    variable_type: str | None = Query(None),
    user=Depends(verify_api_key),
) -> list[dict]:
    conn = _conn()
    rows = storage.latest_helper_rows(conn, survey_id, legacy=False)
    if domain:
        rows = [r for r in rows if r.get("Domain") and domain in r["Domain"]]
    if variable_type:
        rows = [r for r in rows if r.get("VariableType") == variable_type]
    return rows


def _format_rows(rows: list[dict], fmt: str, slug: str):
    if fmt == "json":
        return JSONResponse(rows)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    w.writeheader()
    for r in rows:
        w.writerow(r)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{slug}.csv"'},
    )
