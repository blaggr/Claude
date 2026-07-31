#!/usr/bin/env python3
"""Pick the agencies most in need of a refresh this cycle.

Ranks agencies by (1) fewest core metrics filled, then (2) staleness
(oldest latest period_year), then (3) oldest collected_at. Prints the top N
agency_ids for the autonomous run to work through.

Usage: python agent/pick_targets.py [N]   (default N=8)
"""
from __future__ import annotations
import os, sqlite3, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "db", "cww.db")
CORE = ["caseworker_turnover_rate_pct", "vacancy_rate_pct",
        "avg_caseload_per_caseworker", "recommended_caseload_standard",
        "caseworker_entry_salary_usd", "children_in_foster_care"]


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    con = sqlite3.connect(DB)
    agencies = con.execute(
        "SELECT agency_id, state FROM agencies WHERE jurisdiction_level='state'").fetchall()
    scored = []
    for aid, st in agencies:
        keys = {r[0] for r in con.execute(
            "SELECT DISTINCT metric_key FROM metrics WHERE agency_id=?", (aid,)).fetchall()}
        n_core = sum(1 for k in CORE if k in keys)
        latest = con.execute(
            "SELECT MAX(period_year) FROM metrics WHERE agency_id=?", (aid,)).fetchone()[0] or 0
        # lower n_core and older latest => higher priority
        scored.append((n_core, latest, aid, st))
    scored.sort(key=lambda x: (x[0], x[1]))
    con.close()
    print("# Refresh targets this cycle (highest priority first):")
    for n_core, latest, aid, st in scored[:n]:
        print(f"{aid}\t{st}\tcore_filled={n_core}/6\tlatest_year={latest or '-'}")


if __name__ == "__main__":
    main()
