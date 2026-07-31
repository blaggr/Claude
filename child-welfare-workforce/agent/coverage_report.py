#!/usr/bin/env python3
"""Regenerate docs/COVERAGE.md from the built database.

Summarizes, per jurisdiction, how many distinct metrics are populated and the
freshness of the data, so the agent (and humans) can see where the gaps are.
"""
from __future__ import annotations
import os, sqlite3
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "db", "cww.db")
OUT = os.path.join(ROOT, "docs", "COVERAGE.md")

# Core workforce metrics we most want filled for every agency.
CORE = [
    "caseworker_turnover_rate_pct", "vacancy_rate_pct",
    "avg_caseload_per_caseworker", "recommended_caseload_standard",
    "caseworker_entry_salary_usd", "children_in_foster_care",
]


def main() -> None:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    agencies = con.execute(
        "SELECT agency_id, state, agency_name, admin_structure "
        "FROM agencies WHERE jurisdiction_level='state' ORDER BY state").fetchall()

    rows = []
    total_core = 0
    for a in agencies:
        keys = {r[0] for r in con.execute(
            "SELECT DISTINCT metric_key FROM metrics WHERE agency_id=?",
            (a["agency_id"],)).fetchall()}
        n_all = con.execute(
            "SELECT COUNT(*) FROM metrics WHERE agency_id=?",
            (a["agency_id"],)).fetchone()[0]
        n_core = sum(1 for k in CORE if k in keys)
        total_core += n_core
        latest = con.execute(
            "SELECT MAX(period_year) FROM metrics WHERE agency_id=?",
            (a["agency_id"],)).fetchone()[0]
        rows.append((a["state"], n_all, n_core, latest or "-"))

    n_states = len(agencies)
    n_with = sum(1 for r in rows if r[1] > 0)
    lines = []
    lines.append("# Coverage Tracker\n")
    lines.append(f"_Generated {date.today().isoformat()} by agent/coverage_report.py_\n")
    lines.append(f"- Jurisdictions (state-level): **{n_states}**")
    lines.append(f"- Jurisdictions with >=1 metric: **{n_with}**")
    lines.append(f"- Core-metric fill: **{total_core}/{n_states*len(CORE)}** "
                 f"({100*total_core//(n_states*len(CORE))}%)")
    lines.append(f"\nCore metrics tracked: {', '.join(CORE)}\n")
    lines.append("| State | Total metrics | Core filled (/6) | Latest year |")
    lines.append("|-------|---------------|------------------|-------------|")
    for st, n_all, n_core, latest in rows:
        flag = "" if n_core >= 4 else (" ⚠️" if n_all else " ❌")
        lines.append(f"| {st}{flag} | {n_all} | {n_core} | {latest} |")
    con.close()
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
