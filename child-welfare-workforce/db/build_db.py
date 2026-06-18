#!/usr/bin/env python3
"""Build the Child Welfare Workforce SQLite database from the versioned CSVs.

Usage:
    python db/build_db.py            # build db/cww.db from data/*.csv
    python db/build_db.py --check    # validate CSVs only, no DB write (CI gate)

The CSVs under /data are the source of truth. This script is deterministic:
given the same CSVs it always produces the same database, so the build can run
in CI and the result is fully reproducible.
"""
from __future__ import annotations

import argparse
import csv
import os
import sqlite3
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SCHEMA = os.path.join(ROOT, "schema", "schema.sql")
DB_PATH = os.path.join(ROOT, "db", "cww.db")

VALID_UNITS = {"pct", "count", "ratio", "usd", "years", "days", "hours", ""}
VALID_CONF = {"high", "medium", "low", ""}

# Keys allowed in the metrics table. Mirror of schema/data_dictionary.md.
KNOWN_METRIC_KEYS = {
    "caseworker_headcount", "caseworker_fte", "budgeted_caseworker_positions",
    "vacancy_count", "vacancy_rate_pct", "supervisor_count",
    "supervisor_to_caseworker_ratio",
    "caseworker_turnover_rate_pct", "supervisor_turnover_rate_pct",
    "avg_tenure_years", "time_to_fill_days", "preventable_turnover_rate_pct",
    "avg_caseload_per_caseworker", "recommended_caseload_standard",
    "pct_caseworkers_over_standard", "children_in_foster_care",
    "children_served_total", "cps_referrals_annual", "cps_investigations_annual",
    "caseworker_entry_salary_usd", "caseworker_median_salary_usd",
    "caseworker_salary_max_usd", "min_education_required", "licensure_required",
    "pct_staff_with_social_work_degree", "annual_preservice_training_hours",
    "pct_staff_female", "pct_staff_bipoc",
    "bls_social_workers_employment", "bls_social_workers_mean_wage_usd",
    "bls_social_workers_median_wage_usd",
    "admin_structure", "county_data_availability",
    # --- Expansion: Tier 1 + Tier 2 (docs/EXPANSION_OPTIONS.md) ---
    "bls_metro_median_wage_usd",                 # T1 #1 (metro benchmark)
    "census_public_welfare_employment",          # T1 #2 ASPEP
    "census_public_welfare_payroll_monthly_usd", # T1 #2 ASPEP
    "ipeds_bsw_completions",                      # T1 #3 pipeline supply
    "ipeds_msw_completions",                      # T1 #3 pipeline supply
    "title_iv_e_partnership",                     # T1 #4 (text: program/partner)
    "title_iv_e_stipends_annual",                # T1 #4
    "caseworker_salary_step_count",              # T1 #5 salary schedule depth
    "cw_job_postings_open",                       # T2 #6 vacancy signal
    "agency_personnel_budget_usd",               # T2 #7
    "funded_caseworker_positions",               # T2 #7
    "aswb_licensed_social_workers",              # T2 #8
    "children_per_caseworker_derived",           # T2 #9 derived workload
    "investigations_per_investigator_derived",   # T2 #9 derived workload
    "cfsr_pip_workforce_measure",                # T2 #10 (text)
}


def read_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def validate(agencies: list[dict], metrics: list[dict]) -> list[str]:
    errors: list[str] = []
    agency_ids = {a["agency_id"] for a in agencies}

    for i, m in enumerate(metrics, start=2):  # row 2 = first data row
        aid = m.get("agency_id", "").strip()
        if aid not in agency_ids:
            errors.append(f"metrics row {i}: unknown agency_id '{aid}'")
        key = m.get("metric_key", "").strip()
        if key not in KNOWN_METRIC_KEYS:
            errors.append(f"metrics row {i}: unknown metric_key '{key}'")
        unit = (m.get("unit") or "").strip()
        if unit not in VALID_UNITS:
            errors.append(f"metrics row {i}: bad unit '{unit}'")
        conf = (m.get("confidence") or "").strip().lower()
        if conf not in VALID_CONF:
            errors.append(f"metrics row {i}: bad confidence '{conf}'")
        vn = (m.get("value_numeric") or "").strip()
        vt = (m.get("value_text") or "").strip()
        if not vn and not vt:
            errors.append(f"metrics row {i}: row has neither value_numeric nor value_text")
        if vn:
            try:
                float(vn)
            except ValueError:
                errors.append(f"metrics row {i}: value_numeric '{vn}' not a number")
        # Provenance is mandatory for anything that isn't a structural descriptor.
        if key not in {"admin_structure", "county_data_availability"}:
            if not (m.get("source_url") or "").strip():
                errors.append(f"metrics row {i}: missing source_url for '{key}'")
    return errors


def build(agencies: list[dict], metrics: list[dict]) -> None:
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    with open(SCHEMA, encoding="utf-8") as f:
        con.executescript(f.read())

    con.executemany(
        """INSERT INTO agencies
           (agency_id, jurisdiction_level, state, county, fips, agency_name,
            agency_url, admin_structure, population, notes)
           VALUES (:agency_id,:jurisdiction_level,:state,:county,:fips,
                   :agency_name,:agency_url,:admin_structure,:population,:notes)""",
        [{k: (a.get(k) or None) for k in
          ["agency_id", "jurisdiction_level", "state", "county", "fips",
           "agency_name", "agency_url", "admin_structure", "population", "notes"]}
         for a in agencies],
    )

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for m in metrics:
        rows.append({
            "agency_id": m["agency_id"].strip(),
            "metric_key": m["metric_key"].strip(),
            "value_numeric": float(m["value_numeric"]) if (m.get("value_numeric") or "").strip() else None,
            "value_text": (m.get("value_text") or "").strip() or None,
            "unit": (m.get("unit") or "").strip() or None,
            "period_year": int(m["period_year"]) if (m.get("period_year") or "").strip().isdigit() else None,
            "as_of_date": (m.get("as_of_date") or "").strip() or None,
            "source_name": (m.get("source_name") or "").strip() or None,
            "source_url": (m.get("source_url") or "").strip() or None,
            "source_pub_date": (m.get("source_pub_date") or "").strip() or None,
            "confidence": (m.get("confidence") or "").strip().lower() or None,
            "notes": (m.get("notes") or "").strip() or None,
            "collected_at": (m.get("collected_at") or "").strip() or now,
        })
    con.executemany(
        """INSERT INTO metrics
           (agency_id, metric_key, value_numeric, value_text, unit, period_year,
            as_of_date, source_name, source_url, source_pub_date, confidence,
            notes, collected_at)
           VALUES (:agency_id,:metric_key,:value_numeric,:value_text,:unit,
                   :period_year,:as_of_date,:source_name,:source_url,
                   :source_pub_date,:confidence,:notes,:collected_at)""",
        rows,
    )
    con.commit()

    # Coverage summary
    n_states = con.execute(
        "SELECT COUNT(*) FROM agencies WHERE jurisdiction_level='state'").fetchone()[0]
    n_counties = con.execute(
        "SELECT COUNT(*) FROM agencies WHERE jurisdiction_level='county'").fetchone()[0]
    n_metrics = con.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
    n_with_data = con.execute(
        "SELECT COUNT(DISTINCT agency_id) FROM metrics").fetchone()[0]
    con.close()
    print(f"Built {DB_PATH}")
    print(f"  agencies: {n_states} state + {n_counties} county")
    print(f"  metric observations: {n_metrics}")
    print(f"  agencies with >=1 metric: {n_with_data}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="validate only")
    args = ap.parse_args()

    agencies = read_csv(os.path.join(DATA, "agencies.csv"))
    metrics = read_csv(os.path.join(DATA, "metrics.csv"))
    # Derived metrics are regenerated (not hand-edited) by agent/derive_metrics.py
    # and kept in a separate file so they stay idempotent across rebuilds.
    metrics += read_csv(os.path.join(DATA, "derived_metrics.csv"))
    if not agencies:
        print("ERROR: data/agencies.csv missing or empty", file=sys.stderr)
        return 1

    errors = validate(agencies, metrics)
    if errors:
        print(f"VALIDATION FAILED ({len(errors)} issues):", file=sys.stderr)
        for e in errors[:100]:
            print("  - " + e, file=sys.stderr)
        return 2
    print(f"Validation passed: {len(agencies)} agencies, {len(metrics)} metric rows.")

    if not args.check:
        build(agencies, metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
