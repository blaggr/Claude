#!/usr/bin/env python3
"""Nightly reconcile job: pull Rob-edited rows from Notion back into SQLite.

The intent is to preserve human edits made in the Notion UI (Flag = Confirmed,
Domain reclassification, Notes) without losing the canonical ingestion-run
history. We do NOT mutate existing variables rows — instead we create a new
"manual" ingestion_run whose variables capture the merged state. The previous
auto-ingested run remains for audit.

Conflicts (Notion says Domain=A, SQLite has Domain=B for the same variable in
the same survey) are written to ``sync_conflicts.jsonl`` for human review.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from codebook_builder import storage  # noqa: E402
from codebook_builder.normalize import PARSER_VERSION  # noqa: E402

CONFLICTS_PATH = Path(os.environ.get("CODEBOOK_CONFLICTS", "sync_conflicts.jsonl"))


def main() -> int:
    # Placeholder — implementation lands with Phase 4. Skeleton is here so
    # cron can be wired up early and the schema/migration story is in place.
    print("[sync_from_notion] not yet implemented; planned for Phase 4.")
    print(f"[sync_from_notion] conflicts would be written to {CONFLICTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
