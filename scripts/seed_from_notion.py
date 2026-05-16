#!/usr/bin/env python3
"""Backfill the SQLite codebook DB from the existing AWE Notion DB.

Reads the Variables and Instruments data sources in the AWE Evaluation Database
and inserts a single seed ingestion run per (survey, instrument) pair so today's
Notion content is queryable from Alteryx via v_helper_modern.

Usage::

    export NOTION_API_KEY=secret_xxx
    python scripts/seed_from_notion.py

After this finishes, ``codebookctl pull <survey_id> --format csv`` will return
rows for every survey already documented in the AWE Notion DB.
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict

# Allow running this script directly from the repo root
sys.path.insert(0, str((__import__("pathlib").Path(__file__).resolve().parent.parent)))

from codebook_builder import storage  # noqa: E402
from codebook_builder.notion_sync import (  # noqa: E402
    INSTRUMENTS_DATA_SOURCE,
    VARIABLES_DATA_SOURCE,
)
from codebook_builder.normalize import PARSER_VERSION  # noqa: E402
from codebook_builder.storage import Variable  # noqa: E402


def _client():
    try:
        from notion_client import Client  # type: ignore
    except ImportError as e:
        raise SystemExit("Install notion-client first: pip install notion-client") from e
    token = os.environ.get("NOTION_API_KEY")
    if not token:
        raise SystemExit("NOTION_API_KEY is not set.")
    return Client(auth=token)


def _all_pages(notion, data_source_id: str) -> list[dict]:
    pages: list[dict] = []
    cursor: str | None = None
    while True:
        kwargs = {"data_source_id": data_source_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        res = notion.data_sources.query(**kwargs)
        pages.extend(res.get("results", []))
        if not res.get("has_more"):
            break
        cursor = res.get("next_cursor")
    return pages


def _text(prop: dict | None) -> str | None:
    if not prop:
        return None
    parts = prop.get("rich_text") or prop.get("title") or []
    out = "".join((p.get("plain_text") or "") for p in parts).strip()
    return out or None


def _select(prop: dict | None) -> str | None:
    if not prop:
        return None
    s = prop.get("select")
    return s.get("name") if s else None


def _multi_select(prop: dict | None) -> str | None:
    if not prop:
        return None
    items = prop.get("multi_select") or []
    return ", ".join(i["name"] for i in items) or None


def _checkbox(prop: dict | None) -> bool:
    return bool((prop or {}).get("checkbox"))


def _relation_ids(prop: dict | None) -> list[str]:
    if not prop:
        return []
    return [r["id"] for r in (prop.get("relation") or [])]


def main() -> int:
    notion = _client()
    conn = storage.connect()
    storage.run_migrations(conn)

    print("[seed] pulling Notion Instruments...")
    instruments = _all_pages(notion, INSTRUMENTS_DATA_SOURCE)
    instrument_meta: dict[str, dict] = {}
    for page in instruments:
        props = page.get("properties", {})
        title = _text(props.get("Name") or props.get("Title") or props.get("Instrument Name"))
        if not title:
            continue
        instrument_meta[page["id"]] = {
            "page_id": page["id"],
            "name": title,
            "role": _select(props.get("Role")),
        }
    print(f"[seed] {len(instrument_meta)} instruments")

    print("[seed] pulling Notion Variables...")
    variables = _all_pages(notion, VARIABLES_DATA_SOURCE)
    print(f"[seed] {len(variables)} variable rows")

    # Group variables by their first linked instrument; everything else gets a synthetic survey.
    grouped: dict[str, list[Variable]] = defaultdict(list)
    instrument_of_group: dict[str, str] = {}
    for page in variables:
        props = page.get("properties", {})
        vname = _text(props.get("Variable Name"))
        if not vname:
            continue
        inst_ids = _relation_ids(props.get("Source Instrument"))
        inst_id = inst_ids[0] if inst_ids else "AWE_UNLINKED"
        instrument_of_group[inst_id] = inst_id
        grouped[inst_id].append(Variable(
            variable_name=vname,
            label=_text(props.get("Label")),
            question_text=None,
            variable_type=_select(props.get("Variable Type")),
            domain=_multi_select(props.get("Domain")) or "Other",
            dimension=None,
            scale=_text(props.get("Scale or Response Options")),
            reverse_scored=_checkbox(props.get("Reverse Scored")),
            derivation_logic=_text(props.get("Derivation Logic")),
            source_instrument=instrument_meta.get(inst_id, {}).get("name"),
            cours=None,
            notes=_text(props.get("Notes")),
            flag=_select(props.get("Flag")),
            position=None,
        ))

    inserted = 0
    for inst_id, vars_ in grouped.items():
        meta = instrument_meta.get(inst_id, {"name": "Unlinked AWE Variables", "role": None})
        # Synthesize a survey per instrument; later runs can fold these into proper survey rows
        survey_id = f"awe-notion::{inst_id}"
        with storage.transaction(conn):
            storage.upsert_survey(
                conn,
                survey_id=survey_id,
                title=meta["name"],
                owner="AWE Evaluation Database (Notion)",
            )
            storage.upsert_instrument(
                conn,
                instrument_id=inst_id,
                survey_id=survey_id,
                name=meta["name"],
                role=meta.get("role"),
            )
            run_id = storage.start_run(
                conn,
                survey_id=survey_id,
                source="notion-seed",
                source_uri=f"notion://{inst_id}",
                parser_version=PARSER_VERSION,
                claude_model=None,
                triggered_by="seed_from_notion.py",
            )
            n = storage.insert_variables(
                conn,
                run_id=run_id,
                survey_id=survey_id,
                instrument_id=inst_id,
                variables=vars_,
            )
            storage.finish_run(
                conn,
                run_id=run_id,
                status="complete",
                n_variables=n,
                notes=f"Seeded {n} variables from Notion data source {inst_id}",
            )
            inserted += n

    print(f"[seed] inserted {inserted} variables across {len(grouped)} instrument(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
