#!/usr/bin/env python3
"""Generate derived workforce metrics from the primary observations.

Expansion option Tier 2 #9: where a state publishes both a staff count and a
demand figure but no comparable workload ratio, compute one so states are
comparable. Output is written to data/derived_metrics.csv (overwritten each
run, so it stays idempotent) and folded into the DB by db/build_db.py.

Derived metrics:
- children_per_caseworker_derived = children_in_foster_care / caseworker_headcount
- investigations_per_investigator_derived = cps_investigations_annual / caseworker_headcount

Confidence is the lower of the two input rows' confidence. The note records the
exact inputs and years so the derivation is auditable. Nothing is invented:
a derived row only appears when BOTH inputs exist with numeric values.
"""
from __future__ import annotations
import csv, os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SRC = os.path.join(DATA, "metrics.csv")
OUT = os.path.join(DATA, "derived_metrics.csv")
REPO = "https://github.com/blaggr/Claude/tree/main/child-welfare-workforce"
RANK = {"high": 3, "medium": 2, "low": 1, "": 0}
HEADER = ["agency_id", "metric_key", "value_numeric", "value_text", "unit",
          "period_year", "as_of_date", "source_name", "source_url",
          "source_pub_date", "confidence", "notes", "collected_at"]

DERIVATIONS = [
    ("children_per_caseworker_derived", "children_in_foster_care",
     "caseworker_headcount", "ratio"),
    ("investigations_per_investigator_derived", "cps_investigations_annual",
     "caseworker_headcount", "ratio"),
]


def latest_numeric(rows, agency, key):
    """Most recent numeric value for (agency, key)."""
    best = None
    for r in rows:
        if r["agency_id"] == agency and r["metric_key"] == key and (r.get("value_numeric") or "").strip():
            yr = int(r["period_year"]) if (r.get("period_year") or "").strip().isdigit() else 0
            if best is None or yr >= best[0]:
                best = (yr, float(r["value_numeric"]), (r.get("confidence") or "").strip().lower())
    return best  # (year, value, confidence) or None


def main() -> None:
    with open(SRC, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    agencies = sorted({r["agency_id"] for r in rows})
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    out = []
    for agency in agencies:
        for key, numer_k, denom_k, unit in DERIVATIONS:
            numer = latest_numeric(rows, agency, numer_k)
            denom = latest_numeric(rows, agency, denom_k)
            if not (numer and denom) or denom[1] == 0:
                continue
            val = round(numer[1] / denom[1], 2)
            conf = min(numer[2], denom[2], key=lambda c: RANK.get(c, 0))
            note = (f"Derived = {numer_k} ({numer[1]:.0f}, {numer[0]}) / "
                    f"{denom_k} ({denom[1]:.0f}, {denom[0]}). Headcount scope "
                    f"varies by state; compare with caution.")
            out.append({
                "agency_id": agency, "metric_key": key,
                "value_numeric": val, "value_text": "", "unit": unit,
                "period_year": max(numer[0], denom[0]) or "", "as_of_date": "",
                "source_name": "Derived (CWW-DB)", "source_url": REPO,
                "source_pub_date": "", "confidence": conf,
                "notes": note, "collected_at": now,
            })

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows(out)
    print(f"Wrote {len(out)} derived rows to {OUT}")


if __name__ == "__main__":
    main()
