"""Streamlit dashboard for the qualtrics-awe-analysis skill.

Run with:
    streamlit run app/app.py

Reads QUALTRICS_API_TOKEN and QUALTRICS_DATACENTER from the environment
(or accepts them as session-only overrides via the sidebar). Triggers
the three-stage skill pipeline (pull → analyze → render) via subprocess
and surfaces each step's progress and log output.
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
