#!/usr/bin/env python3
"""OpenAI-powered refresh gatherer for the Child Welfare Workforce Database.

This is the OpenAI alternative to running the cycle on Claude Code. It uses the
OpenAI Responses API with the hosted `web_search` tool to research the stalest
agencies and propose cited workforce-metric rows, following the prime
directives in agent/AGENT_PLAYBOOK.md (never fabricate; cite everything;
controlled vocabulary).

Integrity posture: it does NOT edit data/metrics.csv directly. It writes
PROPOSED rows to data/incoming/openai_proposed.csv. The workflow opens a draft
PR with that file so a human (or a later step) reviews before anything enters
the canonical dataset.

Env:
  OPENAI_API_KEY   (required)
  OPENAI_MODEL     (default "gpt-4.1"; pick a model your account can use that
                    supports the web_search tool, e.g. gpt-4.1 / gpt-4o /
                    a current reasoning model)
  CWW_TARGET_COUNT (default 8)

Setup in CI: `pip install openai`. Fails safe (exit 0) so a flaky API or an
unavailable model never breaks the run; the message says what to fix.
"""
from __future__ import annotations
import csv, json, os, subprocess, sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "incoming", "openai_proposed.csv")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1")
N = int(os.environ.get("CWW_TARGET_COUNT", "8"))
HEADER = ["agency_id","metric_key","value_numeric","value_text","unit","period_year",
          "as_of_date","source_name","source_url","source_pub_date","confidence","notes","collected_at"]

METRIC_KEYS = ("caseworker_headcount, caseworker_fte, budgeted_caseworker_positions, "
    "vacancy_count, vacancy_rate_pct, supervisor_count, supervisor_to_caseworker_ratio, "
    "caseworker_turnover_rate_pct, supervisor_turnover_rate_pct, avg_tenure_years, "
    "time_to_fill_days, avg_caseload_per_caseworker, recommended_caseload_standard, "
    "pct_caseworkers_over_standard, children_in_foster_care, cps_referrals_annual, "
    "cps_investigations_annual, caseworker_entry_salary_usd, caseworker_median_salary_usd, "
    "caseworker_salary_max_usd, min_education_required, licensure_required, "
    "annual_preservice_training_hours, bls_social_workers_employment, "
    "bls_social_workers_mean_wage_usd, bls_social_workers_median_wage_usd")


def pick_targets() -> list[str]:
    try:
        out = subprocess.run([sys.executable, os.path.join(ROOT, "agent", "pick_targets.py"), str(N)],
                             capture_output=True, text=True, timeout=60).stdout
        return [ln.split("\t")[0] for ln in out.splitlines() if ln.startswith("US-")][:N]
    except Exception:
        return []


def prompt_for(agency_id: str) -> str:
    return (
        f"You are gathering U.S. child welfare WORKFORCE data for agency_id {agency_id} "
        f"(the public child welfare agency for that state). Use web search to find the most "
        f"recent, CITABLE figures from official sources (state APSR/CFSP, legislative audits, "
        f"agency dashboards, Casey/QIC-WD/KIDS COUNT, ACF, BLS OEWS 21-1021).\n\n"
        f"RULES: Never fabricate. Only include a value if you can cite a real, resolvable source_url. "
        f"Leave unknowns out. Use these exact metric_key values only: {METRIC_KEYS}.\n\n"
        f"Return ONLY a JSON array (no prose). Each element:\n"
        f'{{"agency_id":"{agency_id}","metric_key":"...","value_numeric":<number or null>,'
        f'"value_text":"<text or empty>","unit":"pct|count|ratio|usd|years|days|hours|",'
        f'"period_year":<year>,"as_of_date":"","source_name":"...","source_url":"https://...",'
        f'"source_pub_date":"","confidence":"high|medium|low","notes":"<brief caveat>"}}'
    )


def gather(client, agency_id: str) -> list[dict]:
    resp = client.responses.create(
        model=MODEL,
        tools=[{"type": "web_search"}],
        input=prompt_for(agency_id),
    )
    text = getattr(resp, "output_text", None) or ""
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < 0:
        return []
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return []


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY not set; nothing to do.", file=sys.stderr)
        return 0
    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        print("openai SDK not installed (pip install openai); skipping.", file=sys.stderr)
        return 0

    targets = pick_targets()
    if not targets:
        print("No targets resolved; skipping.", file=sys.stderr)
        return 0
    client = OpenAI()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for aid in targets:
        try:
            for r in gather(client, aid):
                if not r.get("source_url") or not r.get("metric_key"):
                    continue  # enforce: no citation, no row
                r.setdefault("agency_id", aid)
                r["collected_at"] = now
                rows.append({k: r.get(k, "") for k in HEADER})
        except Exception as e:  # noqa: BLE001 — fail safe per-agency
            print(f"{aid}: gather failed ({e}); skipping.", file=sys.stderr)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADER); w.writeheader(); w.writerows(rows)
    print(f"openai_refresh: proposed {len(rows)} rows across {len(targets)} agencies -> {OUT}")
    print("Review data/incoming/openai_proposed.csv before merging into data/metrics.csv.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
