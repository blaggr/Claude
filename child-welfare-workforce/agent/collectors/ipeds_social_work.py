#!/usr/bin/env python3
"""Tier 1 #3 — social work degree-completion pipeline supply, by state.

Source: Urban Institute Education Data API (mirrors NCES IPEDS), which exposes a
clean JSON REST API (no key). We pull completions for CIP code 44.07
(Social Work) and aggregate BSW (award level 5, Bachelor's) and MSW (award
level 7, Master's) by state.

API: https://educationdata.urban.org/documentation/colleges.html

Runs in the weekly GitHub Action (needs outbound network). Writes rows in the
CWW schema to data/incoming/ipeds_social_work.csv for the agent to review before
merging into data/metrics.csv. Fails safe (exit 0, message) so a flaky API
never breaks the build. VALIDATE the first run's output before trusting it:
confirm award-level codes and the latest available year on the API docs.
"""
from __future__ import annotations
import csv, json, os, sys, urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "incoming", "ipeds_social_work.csv")
YEAR = int(os.environ.get("IPEDS_YEAR", "2022"))  # latest finalized completions year
CIP_SOCIAL_WORK = "4407"
AWARD = {5: ("ipeds_bsw_completions", "BSW"), 7: ("ipeds_msw_completions", "MSW")}
FIPS_TO_USPS = {  # state FIPS -> USPS (for agency_id US-<USPS>)
    "01":"AL","02":"AK","04":"AZ","05":"AR","06":"CA","08":"CO","09":"CT","10":"DE",
    "11":"DC","12":"FL","13":"GA","15":"HI","16":"ID","17":"IL","18":"IN","19":"IA",
    "20":"KS","21":"KY","22":"LA","23":"ME","24":"MD","25":"MA","26":"MI","27":"MN",
    "28":"MS","29":"MO","30":"MT","31":"NE","32":"NV","33":"NH","34":"NJ","35":"NM",
    "36":"NY","37":"NC","38":"ND","39":"OH","40":"OK","41":"OR","42":"PA","44":"RI",
    "45":"SC","46":"SD","47":"TN","48":"TX","49":"UT","50":"VT","51":"VA","53":"WA",
    "54":"WV","55":"WI","56":"WY"}
HEADER = ["agency_id","metric_key","value_numeric","value_text","unit","period_year",
          "as_of_date","source_name","source_url","source_pub_date","confidence","notes","collected_at"]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "cww-db/0.2"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main() -> int:
    base = ("https://educationdata.urban.org/api/v1/college-university/ipeds/"
            f"completions-cip-2/{YEAR}/")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # state FIPS -> {metric_key: total}
    totals: dict[str, dict[str, int]] = {}
    try:
        for level, (key, _label) in AWARD.items():
            url = f"{base}?cipcode_2={CIP_SOCIAL_WORK}&award_level={level}"
            while url:
                page = fetch(url)
                for row in page.get("results", []):
                    fips = str(row.get("fips", "")).zfill(2)
                    n = row.get("awards_6_to_8") or row.get("completions") or 0
                    if fips in FIPS_TO_USPS and n:
                        totals.setdefault(fips, {}).setdefault(key, 0)
                        totals[fips][key] += int(n)
                url = page.get("next")
    except Exception as e:  # noqa: BLE001 — fail safe
        print(f"ipeds_social_work: fetch failed ({e}); wrote nothing.", file=sys.stderr)
        return 0

    rows = []
    for fips, by_key in sorted(totals.items()):
        usps = FIPS_TO_USPS[fips]
        for key, total in by_key.items():
            rows.append({
                "agency_id": f"US-{usps}", "metric_key": key,
                "value_numeric": total, "value_text": "", "unit": "count",
                "period_year": YEAR, "as_of_date": "",
                "source_name": "Urban Institute Education Data API (IPEDS completions, CIP 44.07)",
                "source_url": "https://educationdata.urban.org/documentation/colleges.html",
                "source_pub_date": "", "confidence": "high",
                "notes": "Statewide social work degree completions (pipeline supply), not agency-specific.",
                "collected_at": now,
            })
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADER); w.writeheader(); w.writerows(rows)
    print(f"ipeds_social_work: wrote {len(rows)} rows to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
