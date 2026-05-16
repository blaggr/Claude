"""Streamlit dashboard for the qualtrics-awe-analysis skill.

Run with:
    streamlit run app/app.py

Reads QUALTRICS_API_TOKEN and QUALTRICS_DATACENTER from the environment
(or accepts them as session-only overrides via the sidebar). Triggers
the three-stage skill pipeline (pull → analyze → render) via subprocess
and surfaces each step's progress and log output.

Also hosts the "Build helper file" tab — the codebook generator UI that wraps
codebook_builder + the FastAPI service.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / ".claude" / "skills" / "qualtrics-awe-analysis"
SCRIPTS_DIR = SKILL_DIR / "scripts"
REPORTS_ROOT = REPO_ROOT / "awe-reports"

# Make the codebook_builder package importable when running streamlit from repo root
sys.path.insert(0, str(REPO_ROOT))

ROLES = ["post", "pre", "followup"]


def slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.strip().lower())
    return re.sub(r"-+", "-", s).strip("-") or "awe"


def list_past_runs() -> list[dict]:
    if not REPORTS_ROOT.exists():
        return []
    runs = []
    for d in sorted(REPORTS_ROOT.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        meta_path = d / "metadata.json"
        report_path = d / "AWE-report.html"
        meta = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
            except Exception:
                meta = {}
        runs.append({
            "dir": d,
            "name": d.name,
            "title": meta.get("title", d.name),
            "surveys": meta.get("surveys", []),
            "created_at": meta.get("created_at", ""),
            "has_report": report_path.exists(),
            "report_path": report_path,
        })
    return runs


def run_step(cmd: list[str], env: dict, log_area, label: str) -> bool:
    log_area.markdown(f"**{label}**")
    log_box = log_area.empty()
    buf: list[str] = []

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, env=env,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        buf.append(line.rstrip())
        log_box.code("\n".join(buf[-30:]) or " ", language="text")
    proc.wait()
    if proc.returncode != 0:
        log_area.error(f"{label} failed (exit {proc.returncode})")
        return False
    return True


def run_pipeline(surveys: list[dict], join_key: str, title: str, env_overrides: dict) -> dict | None:
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = slugify(title)
    out_dir = REPORTS_ROOT / f"{slug}-{timestamp}"
    raw_dir = out_dir / "raw"
    processed_dir = out_dir / "processed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "AWE-report.html"

    env = os.environ.copy()
    env.update({k: v for k, v in env_overrides.items() if v})

    pull_script = str(SCRIPTS_DIR / "pull_qualtrics.py")
    analyze_script = str(SCRIPTS_DIR / "analyze.py")
    render_script = str(SCRIPTS_DIR / "render_report.py")

    log_area = st.container()
    progress = st.progress(0.0, text="Starting...")
    total = len(surveys) + 2

    for i, s in enumerate(surveys):
        progress.progress(i / total, text=f"Pulling {s['role']}: {s['identifier']}")
        ok = run_step(
            [sys.executable, pull_script, "--survey", s["identifier"], "--role", s["role"], "--out", str(raw_dir)],
            env, log_area, f"Step 1.{i+1} · Pull Qualtrics — {s['role']}: {s['identifier']}",
        )
        if not ok:
            return None

    progress.progress(len(surveys) / total, text="Analyzing responses...")
    ok = run_step(
        [sys.executable, analyze_script, "--raw", str(raw_dir), "--join-key", join_key, "--out", str(processed_dir)],
        env, log_area, "Step 2 · Classify questions and compute stats",
    )
    if not ok:
        return None

    progress.progress((len(surveys) + 1) / total, text="Rendering dashboard...")
    ok = run_step(
        [sys.executable, render_script, "--processed", str(processed_dir), "--out", str(report_path), "--title", title],
        env, log_area, "Step 3 · Render HTML dashboard",
    )
    if not ok:
        return None

    progress.progress(1.0, text="Done")

    metadata = {
        "title": title,
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "surveys": surveys,
        "join_key": join_key,
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    return {"dir": out_dir, "report": report_path, "metadata": metadata}


def render_environment_status(token: str, datacenter: str):
    cols = st.columns(2)
    with cols[0]:
        if token:
            st.success("QUALTRICS_API_TOKEN: set")
        else:
            st.error("QUALTRICS_API_TOKEN: missing")
    with cols[1]:
        if datacenter:
            st.success(f"QUALTRICS_DATACENTER: {datacenter}")
        else:
            st.error("QUALTRICS_DATACENTER: missing")


# ---------- UI ----------

st.set_page_config(page_title="AWE Survey Analyzer", page_icon=":bar_chart:", layout="wide")

# Session state init
if "surveys" not in st.session_state:
    st.session_state.surveys = [{"identifier": "", "role": "post"}]
if "viewing_run" not in st.session_state:
    st.session_state.viewing_run = None
if "last_run" not in st.session_state:
    st.session_state.last_run = None

# Sidebar: history + env overrides
with st.sidebar:
    st.markdown("### Past runs")
    runs = list_past_runs()
    if not runs:
        st.caption("No reports yet. Run an analysis to populate this list.")
    for r in runs:
        label = f"{r['title']}"
        sublabel = r["created_at"] or r["name"]
        if st.button(f"{label}\n\n{sublabel}", key=f"view_{r['name']}", use_container_width=True):
            st.session_state.viewing_run = r["name"]
            st.session_state.last_run = None

    st.divider()
    with st.expander("Environment overrides (session-only)"):
        st.caption("Leave empty to use values from your shell environment.")
        override_token = st.text_input("QUALTRICS_API_TOKEN", type="password", value="", key="ov_token")
        override_dc = st.text_input("QUALTRICS_DATACENTER", value="", key="ov_dc",
                                    placeholder="e.g. iad1, fra1, syd1")

resolved_token = (st.session_state.get("ov_token") or os.environ.get("QUALTRICS_API_TOKEN") or "")
resolved_dc = (st.session_state.get("ov_dc") or os.environ.get("QUALTRICS_DATACENTER") or "")
env_overrides = {"QUALTRICS_API_TOKEN": resolved_token, "QUALTRICS_DATACENTER": resolved_dc}

# Decide what to show in main area
view_run_name = st.session_state.get("viewing_run")
selected_run = next((r for r in list_past_runs() if r["name"] == view_run_name), None) if view_run_name else None

st.title("AWE Survey Analyzer")
st.caption("Pull Qualtrics surveys, classify questions against the Kirkpatrick framework, and generate an AWE training evaluation dashboard.")


def render_helper_tab() -> None:
    """Codebook generator tab — wraps codebook_builder + FastAPI."""
    from codebook_builder import storage as cb_storage, normalize as cb_normalize
    from codebook_builder.normalize import PARSER_VERSION

    conn = cb_storage.connect()
    cb_storage.run_migrations(conn)

    st.markdown("### Generate a helper file (codebook)")
    st.caption(
        "Paste a Qualtrics survey ID or title, OR upload a PDF / DOCX. "
        "We pull, normalize, and write to the codebook DB; you can then export "
        "the helper as CSV / XLSX or hand the survey ID to Alteryx via ODBC."
    )

    ingest_kind = st.radio(
        "Source", ["Qualtrics", "PDF / DOCX"], horizontal=True, key="helper_ingest_kind",
    )

    if ingest_kind == "Qualtrics":
        q_arg = st.text_input(
            "Survey ID or title",
            key="helper_qualtrics_arg",
            placeholder="SV_abc123  or  'AWE Coaching e-Learning Post'",
        )
        role = st.selectbox("Role", ROLES, index=0, key="helper_qualtrics_role")
        push = st.checkbox("Also push to AWE Notion DB after ingest", key="helper_push_notion_q")
        use_llm = st.checkbox(
            "Use Claude to normalize (recommended if ANTHROPIC_API_KEY is set)",
            value=bool(os.environ.get("ANTHROPIC_API_KEY")),
            key="helper_use_llm_q",
        )
        if st.button("Run ingest", key="helper_run_q", disabled=not q_arg.strip()):
            _run_qualtrics_ingest(conn, q_arg.strip(), role, push, use_llm)
    else:
        uploaded = st.file_uploader("Survey document", type=["pdf", "docx"], key="helper_doc_file")
        survey_id = st.text_input("Survey slug (used as the key)", key="helper_doc_survey_id",
                                   placeholder="e.g. eag-yearend-2026")
        survey_title = st.text_input("Survey title", key="helper_doc_title")
        role = st.selectbox("Role", ROLES, index=0, key="helper_doc_role")
        push = st.checkbox("Also push to AWE Notion DB after ingest", key="helper_push_notion_d")
        can_run = bool(uploaded and survey_id.strip())
        if not os.environ.get("ANTHROPIC_API_KEY"):
            st.info("Document ingestion requires ANTHROPIC_API_KEY in the environment.")
            can_run = False
        if st.button("Run ingest", key="helper_run_d", disabled=not can_run):
            _run_document_ingest(conn, uploaded, survey_id.strip(), survey_title.strip() or survey_id, role, push)

    st.divider()
    _render_known_surveys(conn)


def _run_qualtrics_ingest(conn, qualtrics_arg: str, role: str, push: bool, use_llm: bool) -> None:
    from codebook_builder.sources import qualtrics as qsrc
    from codebook_builder import normalize as cb_normalize, storage as cb_storage
    from codebook_builder.normalize import PARSER_VERSION

    log = st.empty()
    with st.spinner(f"Resolving Qualtrics survey '{qualtrics_arg}'..."):
        sid, name, definition = qsrc.resolve_and_fetch(qualtrics_arg)
        log.info(f"Resolved: **{name}** (`{sid}`)")
        questions = qsrc.extract_questions(definition)
        log.info(f"Extracted {len(questions)} questions; normalizing...")

    with cb_storage.transaction(conn):
        cb_storage.upsert_survey(conn, survey_id=sid, qualtrics_id=sid, title=name)
        iid = f"{sid}__default"
        cb_storage.upsert_instrument(conn, instrument_id=iid, survey_id=sid, name=name, role=role)
        run_id = cb_storage.start_run(
            conn, survey_id=sid, source="qualtrics", source_uri=sid,
            parser_version=PARSER_VERSION,
            claude_model=cb_normalize.DEFAULT_MODEL if use_llm else None,
            triggered_by="streamlit",
        )

    try:
        vars_ = cb_normalize.normalize_qualtrics_questions(questions, use_llm=use_llm)
        with cb_storage.transaction(conn):
            n = cb_storage.insert_variables(
                conn, run_id=run_id, survey_id=sid, instrument_id=iid, variables=vars_,
            )
            cb_storage.finish_run(conn, run_id=run_id, status="complete", n_variables=n)
        st.success(f"Ingested {n} variables into run #{run_id}.")
    except Exception as e:
        with cb_storage.transaction(conn):
            cb_storage.finish_run(conn, run_id=run_id, status="failed", n_variables=0, notes=str(e)[:500])
        st.error(f"Ingest failed: {e}")
        return

    if push:
        try:
            from codebook_builder import notion_sync
            summary = notion_sync.sync_run(run_id, conn)
            st.success(f"Pushed to Notion: created={summary['created']}, updated={summary['updated']}")
        except Exception as e:
            st.warning(f"Notion sync failed: {e}")

    _show_helper_preview(conn, sid)


def _run_document_ingest(conn, uploaded, survey_id: str, survey_title: str, role: str, push: bool) -> None:
    from codebook_builder.sources import document as docsrc
    from codebook_builder import normalize as cb_normalize, storage as cb_storage
    from codebook_builder.normalize import PARSER_VERSION
    import tempfile

    suffix = ".pdf" if uploaded.name.lower().endswith(".pdf") else ".docx"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
        fh.write(uploaded.read())
        tmp_path = Path(fh.name)

    with st.spinner(f"Parsing {uploaded.name}..."):
        text = docsrc.extract_text(tmp_path)

    with cb_storage.transaction(conn):
        cb_storage.upsert_survey(conn, survey_id=survey_id, title=survey_title)
        iid = f"{survey_id}__default"
        cb_storage.upsert_instrument(conn, instrument_id=iid, survey_id=survey_id, name=survey_title, role=role)
        run_id = cb_storage.start_run(
            conn, survey_id=survey_id,
            source="pdf" if suffix == ".pdf" else "docx",
            source_uri=str(tmp_path),
            parser_version=PARSER_VERSION,
            claude_model=cb_normalize.DEFAULT_MODEL,
            triggered_by="streamlit",
        )

    try:
        vars_ = cb_normalize.normalize_document_text(text)
        with cb_storage.transaction(conn):
            n = cb_storage.insert_variables(conn, run_id=run_id, survey_id=survey_id, instrument_id=iid, variables=vars_)
            cb_storage.finish_run(conn, run_id=run_id, status="complete", n_variables=n)
        st.success(f"Ingested {n} variables into run #{run_id}.")
    except Exception as e:
        with cb_storage.transaction(conn):
            cb_storage.finish_run(conn, run_id=run_id, status="failed", n_variables=0, notes=str(e)[:500])
        st.error(f"Ingest failed: {e}")
        return

    if push:
        try:
            from codebook_builder import notion_sync
            summary = notion_sync.sync_run(run_id, conn)
            st.success(f"Pushed to Notion: created={summary['created']}, updated={summary['updated']}")
        except Exception as e:
            st.warning(f"Notion sync failed: {e}")

    _show_helper_preview(conn, survey_id)


def _render_known_surveys(conn) -> None:
    from codebook_builder import storage as cb_storage
    rows = cb_storage.list_surveys(conn)
    st.markdown("### Known surveys")
    if not rows:
        st.caption("Nothing ingested yet.")
        return
    survey_options = {f"{r['title']}  ({r['survey_id']})": r["survey_id"] for r in rows}
    pick = st.selectbox("Pick a survey to view its helper file", options=list(survey_options.keys()))
    if pick:
        _show_helper_preview(conn, survey_options[pick])


def _show_helper_preview(conn, survey_id: str) -> None:
    from codebook_builder import storage as cb_storage
    rows = cb_storage.latest_helper_rows(conn, survey_id, legacy=False)
    if not rows:
        st.warning(f"No helper rows for {survey_id} yet.")
        return
    st.markdown(f"#### Helper preview — `{survey_id}`")
    st.dataframe(rows, use_container_width=True, height=420)

    runs = cb_storage.runs_for_survey(conn, survey_id)
    with st.expander(f"Ingestion history ({len(runs)} run(s))"):
        st.dataframe(runs, use_container_width=True)

    import csv, io as _io
    buf = _io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    w.writeheader()
    for r in rows:
        w.writerow(r)
    st.download_button(
        "Download CSV (Internal Helper Columns)", data=buf.getvalue(),
        file_name=f"{survey_id}-helper.csv", mime="text/csv",
    )


with st.expander("Build helper file (codebook)", expanded=False):
    render_helper_tab()


if selected_run:
    st.markdown(f"### Viewing: {selected_run['title']}")
    st.caption(f"Generated {selected_run['created_at'] or '(unknown)'} · {len(selected_run['surveys'])} survey(s)")
    cols = st.columns([1, 1, 4])
    with cols[0]:
        if st.button("New run", type="primary"):
            st.session_state.viewing_run = None
            st.rerun()
    with cols[1]:
        if selected_run["has_report"]:
            with open(selected_run["report_path"], "rb") as f:
                st.download_button("Download HTML", f, file_name="AWE-report.html", mime="text/html")
    if selected_run["has_report"]:
        html = selected_run["report_path"].read_text()
        components.html(html, height=1200, scrolling=True)
    else:
        st.warning("This run has no report file.")
    st.stop()

# New-run form
render_environment_status(resolved_token, resolved_dc)
if not resolved_token or not resolved_dc:
    st.info("Set both env vars in your shell before launching streamlit, or enter them in the sidebar (session-only).")

st.markdown("### Surveys to include")
st.caption("Enter a Qualtrics survey ID (starts with `SV_`) or a title substring. Add one row per survey.")

# Dynamic survey rows (outside the form so add/remove takes effect immediately)
to_remove: list[int] = []
for i, s in enumerate(st.session_state.surveys):
    cols = st.columns([5, 2, 1])
    with cols[0]:
        st.session_state.surveys[i]["identifier"] = st.text_input(
            "Survey ID or title", value=s["identifier"], key=f"id_{i}",
            placeholder="SV_abc123  or  'AWE Coaching e-Learning Post'",
            label_visibility="collapsed",
        )
    with cols[1]:
        st.session_state.surveys[i]["role"] = st.selectbox(
            "Role", ROLES, index=ROLES.index(s["role"]),
            key=f"role_{i}", label_visibility="collapsed",
        )
    with cols[2]:
        if st.button("Remove", key=f"rm_{i}", disabled=len(st.session_state.surveys) <= 1):
            to_remove.append(i)

if to_remove:
    for i in sorted(to_remove, reverse=True):
        st.session_state.surveys.pop(i)
    st.rerun()

cols = st.columns([1, 1, 4])
with cols[0]:
    if st.button("+ Add survey"):
        st.session_state.surveys.append({"identifier": "", "role": "followup" if len(st.session_state.surveys) >= 2 else "post"})
        st.rerun()

st.markdown("### Run configuration")
cols = st.columns([3, 2])
with cols[0]:
    title = st.text_input("Report title", value="Academy for Workforce Excellence — Training Evaluation")
with cols[1]:
    join_key = st.text_input("Join key column", value="ParticipantID",
                              help="Column name used to join pre/post/follow-up responses by participant.")

# Validation
valid_surveys = [s for s in st.session_state.surveys if s["identifier"].strip()]
roles_in_use = [s["role"] for s in valid_surveys]
duplicate_roles = {r for r in roles_in_use if roles_in_use.count(r) > 1}

issues: list[str] = []
if not valid_surveys:
    issues.append("Add at least one survey identifier.")
if duplicate_roles:
    issues.append(f"Each role can only be used once. Duplicate role(s): {', '.join(sorted(duplicate_roles))}")
if not resolved_token or not resolved_dc:
    issues.append("QUALTRICS_API_TOKEN and QUALTRICS_DATACENTER must both be set.")

run_disabled = bool(issues)
if issues:
    for msg in issues:
        st.warning(msg)

if st.button("Run analysis", type="primary", disabled=run_disabled):
    result = run_pipeline(valid_surveys, join_key, title, env_overrides)
    if result:
        st.session_state.last_run = result["dir"].name
        st.success(f"Report generated at `{result['report'].relative_to(REPO_ROOT)}`")

# Show the most recent run inline if there's one and we're not viewing history
if st.session_state.get("last_run"):
    latest = next((r for r in list_past_runs() if r["name"] == st.session_state.last_run), None)
    if latest and latest["has_report"]:
        st.divider()
        st.markdown(f"### Latest report: {latest['title']}")
        cols = st.columns([1, 5])
        with cols[0]:
            with open(latest["report_path"], "rb") as f:
                st.download_button("Download HTML", f, file_name="AWE-report.html", mime="text/html")
        components.html(latest["report_path"].read_text(), height=1200, scrolling=True)
