#!/usr/bin/env python3
"""Mirror the CWW database to a Google Sheet.

Source of truth is the repo (data/*.csv → db/cww.db). This pushes a flattened,
human-friendly "latest value per agency/metric" view to a Google Sheet for
easy viewing/sharing.

Setup:
  pip install gspread google-auth
  export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
  export CWW_SHEET_ID=<spreadsheet id shared with the service account>

Run:
  python mirror/to_sheets.py

This is intentionally dependency-light and defensive: if creds/libs are absent
it prints what it WOULD push and exits 0, so the refresh workflow never fails
just because the mirror isn't configured.
"""
from __future__ import annotations
import os, sqlite3, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "db", "cww.db")
SHEET_ID = os.environ.get("CWW_SHEET_ID")


def latest_rows():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """SELECT a.state, a.agency_name, a.admin_structure, m.metric_key,
                  COALESCE(CAST(m.value_numeric AS TEXT), m.value_text) AS value,
                  m.unit, m.period_year, m.confidence, m.source_url
           FROM metrics_latest m JOIN agencies a USING(agency_id)
           ORDER BY a.state, m.metric_key""").fetchall()
    con.close()
    header = ["state", "agency", "admin_structure", "metric", "value",
              "unit", "year", "confidence", "source_url"]
    return header, [list(r) for r in rows]


def main() -> int:
    header, rows = latest_rows()
    if not SHEET_ID:
        print("CWW_SHEET_ID not set — dry run. Would push "
              f"{len(rows)} rows with columns {header}.")
        return 0
    try:
        import gspread  # type: ignore
    except ImportError:
        print("gspread not installed — dry run. Would push "
              f"{len(rows)} rows to sheet {SHEET_ID}.")
        return 0
    gc = gspread.service_account(
        filename=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.sheet1
    ws.clear()
    ws.update([header] + rows)
    print(f"Pushed {len(rows)} rows to Google Sheet {SHEET_ID}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
