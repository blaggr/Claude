#!/usr/bin/env python3
"""Tier 1 #2 — public welfare employment & payroll, by state.

Source: U.S. Census Bureau Annual Survey of Public Employment & Payroll
(ASPEP), an independent, all-states series that serves as a neutral cross-check
on agency-reported staffing. We pull the "Public Welfare" government function
(full-time-equivalent employment and monthly payroll) for state+local govt.

Census API: https://api.census.gov/data.html  (Public Sector / ASPEP)
A CENSUS_API_KEY env var is recommended (free) but not strictly required for
low volume.

Runs in the weekly GitHub Action (needs outbound network). Writes rows in the
CWW schema to data/incoming/census_aspep.csv for review before merge. Fails
safe. VALIDATE the first run: confirm the dataset path, the Public-Welfare
function code, and variable names against the current ASPEP API docs (these
have changed across vintages), then adjust DATASET/FUNCTION/VARS below.
"""
from __future__ import annotations
import csv, json, os, sys, urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "incoming", "census_aspep.csv")
YEAR = os.environ.get("ASPEP_YEAR", "2022")
KEY = os.environ.get("CENSUS_API_KEY", "")

# NOTE: confirm these against https://api.census.gov/data.html for the chosen
# vintage before trusting output. ASPEP variable/function naming has shifted.
DATASET = f"https://api.census.gov/data/{YEAR}/pep/aspep"  # placeholder path
FUNCTION_PUBLIC_WELFARE = "24"   # Census govt function code for Public Welfare
VARS = {"full_time_equivalent_employment": "census_public_welfare_employment",
        "total_march_payroll": "census_public_welfare_payroll_monthly_usd"}
HEADER = ["agency_id","metric_key","value_numeric","value_text","unit","period_year",
          "as_of_date","source_name","source_url","source_pub_date","confidence","notes","collected_at"]


def main() -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    get = ",".join(["NAME", "GOVTYPE", "SVYFUNCTION"] + list(VARS))
    url = f"{DATASET}?get={get}&for=state:*&FUNCTION={FUNCTION_PUBLIC_WELFARE}"
    if KEY:
        url += f"&key={KEY}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "cww-db/0.2"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
    except Exception as e:  # noqa: BLE001 — fail safe
        print(f"census_aspep: fetch failed ({e}); wrote nothing. "
              f"Confirm the ASPEP API path/vars for {YEAR}.", file=sys.stderr)
        return 0

    if not data or len(data) < 2:
        print("census_aspep: empty response; wrote nothing.", file=sys.stderr)
        return 0
    cols = {name: i for i, name in enumerate(data[0])}
    rows = []
    for rec in data[1:]:
        fips = rec[cols.get("state", -1)] if "state" in cols else ""
        for var, key in VARS.items():
            if var not in cols:
                continue
            try:
                val = float(rec[cols[var]])
            except (TypeError, ValueError):
                continue
            rows.append({
                "agency_id": f"US-FIPS{fips}", "metric_key": key,
                "value_numeric": val, "value_text": "",
                "unit": "usd" if "payroll" in key else "count",
                "period_year": YEAR, "as_of_date": "",
                "source_name": "U.S. Census ASPEP (Public Welfare function)",
                "source_url": "https://www.census.gov/programs-surveys/apes.html",
                "source_pub_date": "", "confidence": "high",
                "notes": "State+local Public Welfare function; broader than child welfare. agency_id uses FIPS; map to US-<USPS> on merge.",
                "collected_at": now,
            })
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADER); w.writeheader(); w.writerows(rows)
    print(f"census_aspep: wrote {len(rows)} rows to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
