"""Push canonical Variables into the existing AWE Notion DB.

This is the optional last step of an ingestion run. SQLite is the system of
record; Notion is the human-browseable surface. We do a best-effort upsert: if
a variable with the same (Source Instrument, Variable Name) already exists, we
update it; otherwise we create a new page in the Variables data source.

We deliberately do NOT support arbitrary Notion schema changes here — only the
fields the AWE Evaluation Database already exposes. If the Notion schema
drifts, the upserts will fail loudly and we'll add a migration.

To run::

    export NOTION_API_KEY=secret_xxx
    python -m codebook_builder.notion_sync --run 42

Or call ``sync_run(run_id, conn)`` from Python.
"""
from __future__ import annotations

import os
from typing import Any, Iterable

from . import storage

VARIABLES_DATA_SOURCE = os.environ.get(
    "NOTION_VARIABLES_DATA_SOURCE",
    "24c71b35-f175-4b0d-88ed-0b826157c025",  # AWE Evaluation Database → Variables
)
INSTRUMENTS_DATA_SOURCE = os.environ.get(
    "NOTION_INSTRUMENTS_DATA_SOURCE",
    "6abba03b-ef50-403c-9c49-63b5bc994d05",  # AWE Evaluation Database → Instruments
)


def sync_run(run_id: int, conn) -> dict:
    """Push every variable from ``run_id`` to Notion. Returns a small summary dict."""
    try:
        from notion_client import Client  # type: ignore
    except ImportError as e:
        raise ImportError(
            "notion-client is required for Notion sync. "
            "Run `pip install notion-client` and set NOTION_API_KEY."
        ) from e

    token = os.environ.get("NOTION_API_KEY")
    if not token:
        raise RuntimeError("NOTION_API_KEY is not set; cannot push to Notion.")

    notion = Client(auth=token)

    run = storage.get_run(conn, run_id)
    if run is None:
        raise ValueError(f"No ingestion_run with id={run_id}")

    rows = conn.execute(
        """
        SELECT v.*, s.title AS survey_title, i.name AS instrument_name
        FROM   variables v
        LEFT JOIN surveys     s ON s.survey_id     = v.survey_id
        LEFT JOIN instruments i ON i.instrument_id = v.instrument_id
        WHERE  v.ingestion_run_id = ?
        """,
        (run_id,),
    ).fetchall()

    created = 0
    updated = 0
    skipped = 0
    for row in rows:
        existing = _find_existing_variable(notion, row["variable_name"], row["instrument_id"])
        props = _variable_properties(row)
        if existing:
            notion.pages.update(page_id=existing, properties=props)
            updated += 1
        else:
            notion.pages.create(
                parent={"data_source_id": VARIABLES_DATA_SOURCE},
                properties=props,
            )
            created += 1

    return {
        "run_id": run_id,
        "survey_id": run["survey_id"],
        "n_rows": len(rows),
        "created": created,
        "updated": updated,
        "skipped": skipped,
    }


def _find_existing_variable(notion, variable_name: str, instrument_id: str | None) -> str | None:
    """Return the Notion page id for a Variable with this name (within instrument, if given)."""
    filter_clauses: list[dict] = [
        {"property": "Variable Name", "title": {"equals": variable_name}}
    ]
    query: dict[str, Any] = {
        "data_source_id": VARIABLES_DATA_SOURCE,
        "filter": {"and": filter_clauses},
        "page_size": 5,
    }
    res = notion.data_sources.query(**query)
    pages = res.get("results", [])
    if not pages:
        return None
    if instrument_id is None:
        return pages[0]["id"]
    # Try to disambiguate by Source Instrument relation
    for p in pages:
        rels = (p.get("properties", {}).get("Source Instrument", {}) or {}).get("relation", [])
        for rel in rels:
            if rel.get("id") == instrument_id:
                return p["id"]
    return pages[0]["id"]


def _variable_properties(row) -> dict:
    """Map a SQLite ``variables`` row to Notion property values."""
    return {
        "Variable Name": {"title": [{"text": {"content": row["variable_name"]}}]},
        "Label": _rich_text(row["label"]),
        "Scale or Response Options": _rich_text(row["scale"]),
        "Derivation Logic": _rich_text(row["derivation_logic"]),
        "Notes": _rich_text(row["notes"]),
        "Variable Type": _select(row["variable_type"]),
        "Domain": _multi_select(row["domain"]),
        "Flag": _select(row["flag"]),
        "Reverse Scored": {"checkbox": bool(row["reverse_scored"])},
    }


def _rich_text(value: str | None) -> dict:
    if not value:
        return {"rich_text": []}
    return {"rich_text": [{"text": {"content": value[:1900]}}]}


def _select(value: str | None) -> dict:
    if not value:
        return {"select": None}
    return {"select": {"name": value}}


def _multi_select(value: str | None) -> dict:
    if not value:
        return {"multi_select": []}
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return {"multi_select": [{"name": p} for p in parts]}
