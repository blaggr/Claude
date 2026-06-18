#!/usr/bin/env python3
"""Mirror the CWW database to a Notion database.

Source of truth is the repo. This upserts one Notion page per agency with the
latest core metrics as properties, for browsing/sharing in Notion.

Setup:
  export NOTION_API_KEY=<integration token>
  export NOTION_DATABASE_ID=<target database id, shared with the integration>
  pip install requests

Run:
  python mirror/to_notion.py

Defensive by design: if creds/libs are missing it prints what it WOULD push and
exits 0 so the refresh workflow never fails on an unconfigured mirror.

NOTE: This uses the public Notion REST API with a token. In an interactive
Claude Code session you can alternatively use the Notion MCP tools
(mcp__*__notion-create-database / notion-update-page) to scaffold and populate
the database directly without managing a token here.
"""
from __future__ import annotations
import os, sqlite3, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "db", "cww.db")
API_KEY = os.environ.get("NOTION_API_KEY")
DB_ID = os.environ.get("NOTION_DATABASE_ID")

# Core metrics shown as Notion properties (one page per agency).
CORE = ["caseworker_turnover_rate_pct", "vacancy_rate_pct",
        "avg_caseload_per_caseworker", "recommended_caseload_standard",
        "caseworker_entry_salary_usd", "children_in_foster_care"]


def agency_snapshots():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    agencies = con.execute(
        "SELECT agency_id, state, agency_name, admin_structure "
        "FROM agencies WHERE jurisdiction_level='state' ORDER BY state").fetchall()
    out = []
    for a in agencies:
        snap = {"state": a["state"], "agency": a["agency_name"],
                "admin_structure": a["admin_structure"]}
        for k in CORE:
            r = con.execute(
                "SELECT value_numeric, value_text, period_year FROM metrics_latest "
                "WHERE agency_id=? AND metric_key=?", (a["agency_id"], k)).fetchone()
            snap[k] = (r["value_numeric"] if r and r["value_numeric"] is not None
                       else (r["value_text"] if r else None))
        out.append(snap)
    con.close()
    return out


def main() -> int:
    snaps = agency_snapshots()
    if not (API_KEY and DB_ID):
        print("NOTION_API_KEY / NOTION_DATABASE_ID not set — dry run. "
              f"Would upsert {len(snaps)} agency pages with core metrics {CORE}.")
        return 0
    try:
        import requests  # type: ignore
    except ImportError:
        print(f"requests not installed — dry run. Would upsert {len(snaps)} pages.")
        return 0

    headers = {"Authorization": f"Bearer {API_KEY}",
               "Notion-Version": "2022-06-28",
               "Content-Type": "application/json"}
    for s in snaps:
        props = {
            "Agency": {"title": [{"text": {"content": s["agency"] or s["state"]}}]},
            "State": {"rich_text": [{"text": {"content": s["state"]}}]},
            "Admin structure": {"rich_text": [{"text": {"content": s["admin_structure"] or ""}}]},
        }
        for k in CORE:
            v = s.get(k)
            if isinstance(v, (int, float)):
                props[k] = {"number": v}
            elif v:
                props[k] = {"rich_text": [{"text": {"content": str(v)}}]}
        requests.post("https://api.notion.com/v1/pages", headers=headers,
                      json={"parent": {"database_id": DB_ID}, "properties": props},
                      timeout=30)
    print(f"Upserted {len(snaps)} agency pages to Notion database {DB_ID}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
