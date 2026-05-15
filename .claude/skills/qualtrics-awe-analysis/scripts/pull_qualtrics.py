#!/usr/bin/env python3
"""Pull responses + definition for one Qualtrics survey.

Usage:
    pull_qualtrics.py --survey <id-or-title> --role <pre|post|followup> --out <dir>

Requires:
    QUALTRICS_API_TOKEN, QUALTRICS_DATACENTER in env.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import zipfile
from pathlib import Path

import requests


API_VERSION = "v3"


def base_url() -> str:
    dc = os.environ.get("QUALTRICS_DATACENTER")
    if not dc:
        sys.exit("QUALTRICS_DATACENTER is not set (e.g. iad1, fra1, syd1).")
    return f"https://{dc}.qualtrics.com/API/{API_VERSION}"


def headers() -> dict:
    token = os.environ.get("QUALTRICS_API_TOKEN")
    if not token:
        sys.exit("QUALTRICS_API_TOKEN is not set.")
    return {"X-API-TOKEN": token, "Content-Type": "application/json"}


def retry(callable_, attempts=5, base_delay=2.0):
    last = None
    for i in range(attempts):
        try:
            return callable_()
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status in (429, 500, 502, 503, 504) and i < attempts - 1:
                time.sleep(base_delay * (2 ** i))
                last = e
                continue
            raise
        except requests.RequestException as e:
            if i < attempts - 1:
                time.sleep(base_delay * (2 ** i))
                last = e
                continue
            raise
    if last:
        raise last


def resolve_survey(survey_arg: str) -> tuple[str, str]:
    """Return (surveyId, name). Accepts a survey ID (SV_*) or a title (substring, case-insensitive)."""
    if survey_arg.startswith("SV_"):
        def _fetch():
            r = requests.get(f"{base_url()}/survey-definitions/{survey_arg}/metadata", headers=headers(), timeout=30)
            r.raise_for_status()
            return r.json()
        meta = retry(_fetch)
        name = meta.get("result", {}).get("surveyName", survey_arg)
        return survey_arg, name

    def _list():
        out = []
        offset = None
        while True:
            url = f"{base_url()}/surveys"
            params = {"offset": offset} if offset else {}
            r = requests.get(url, headers=headers(), params=params, timeout=30)
            r.raise_for_status()
            data = r.json().get("result", {})
            out.extend(data.get("elements", []))
            offset = data.get("nextPage")
            if not offset:
                break
            # nextPage from Qualtrics is a full URL with an offset query — parse it
            m = re.search(r"offset=([^&]+)", offset)
            offset = m.group(1) if m else None
            if not offset:
                break
        return out

    surveys = retry(_list)
    needle = survey_arg.strip().lower()
    matches = [s for s in surveys if needle in s.get("name", "").lower()]
    if not matches:
        sys.exit(f"No Qualtrics survey title matched '{survey_arg}'. Provide the SV_... ID instead.")
    if len(matches) > 1:
        listed = "\n".join(f"  - {s['name']}  ({s['id']})" for s in matches[:20])
        sys.exit(f"Title '{survey_arg}' matched {len(matches)} surveys. Re-run with one of these IDs:\n{listed}")
    s = matches[0]
    return s["id"], s["name"]


def fetch_definition(survey_id: str) -> dict:
    def _fetch():
        r = requests.get(f"{base_url()}/survey-definitions/{survey_id}", headers=headers(), timeout=60)
        r.raise_for_status()
        return r.json()
    return retry(_fetch).get("result", {})


def export_responses(survey_id: str, fmt: str = "csv") -> bytes:
    start = lambda: requests.post(
        f"{base_url()}/surveys/{survey_id}/export-responses",
        headers=headers(),
        data=json.dumps({"format": fmt, "useLabels": True, "compress": True}),
        timeout=60,
    )
    r = retry(lambda: _raise(start()))
    progress_id = r.json()["result"]["progressId"]

    while True:
        prog = retry(lambda: _raise(requests.get(
            f"{base_url()}/surveys/{survey_id}/export-responses/{progress_id}",
            headers=headers(), timeout=30,
        )))
        body = prog.json()["result"]
        status = body.get("status")
        if status == "complete":
            file_id = body["fileId"]
            break
        if status == "failed":
            sys.exit(f"Qualtrics export failed: {body}")
        time.sleep(1.5)

    dl = retry(lambda: _raise(requests.get(
        f"{base_url()}/surveys/{survey_id}/export-responses/{file_id}/file",
        headers=headers(), timeout=120,
    )))
    return dl.content


def _raise(r: requests.Response) -> requests.Response:
    r.raise_for_status()
    return r


def unpack_zip(zip_bytes: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        # Pick the first .csv inside
        csv_name = next((n for n in names if n.lower().endswith(".csv")), names[0])
        return zf.read(csv_name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--survey", required=True, help="Qualtrics survey ID (SV_...) or title substring")
    ap.add_argument("--role", default="post", choices=["pre", "post", "followup"])
    ap.add_argument("--out", required=True, help="Output directory for raw CSV + definition JSON")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    survey_id, name = resolve_survey(args.survey)
    print(f"[pull] {args.role}: {name} ({survey_id})", flush=True)

    definition = fetch_definition(survey_id)
    def_path = out_dir / f"{args.role}_{survey_id}.definition.json"
    def_path.write_text(json.dumps({"surveyId": survey_id, "name": name, "role": args.role, "definition": definition}, indent=2))

    zip_bytes = export_responses(survey_id)
    csv_bytes = unpack_zip(zip_bytes)
    csv_path = out_dir / f"{args.role}_{survey_id}.csv"
    csv_path.write_bytes(csv_bytes)

    print(f"[pull] wrote {csv_path.name} and {def_path.name}", flush=True)


if __name__ == "__main__":
    main()
