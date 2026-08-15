"""CLI: trigger a full or incremental reindex from the command line."""
from __future__ import annotations

import argparse
import asyncio
import json

from src.ingest import run_ingest


async def _main(full: bool) -> None:
    stats = await run_ingest(full=full)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Reindex everything regardless of content hashes.")
    args = parser.parse_args()
    asyncio.run(_main(full=args.full))
