from __future__ import annotations

import asyncio
import time
from typing import Any, Dict

from .chunker import chunk_text
from .config import settings
from .crawler import FetchResult, content_hash, crawl
from .extractor import extract
from .store import StateStore, add_document, delete_document


_ingest_lock = asyncio.Lock()
_last_run: Dict[str, Any] = {"running": False, "started_at": None, "finished_at": None, "stats": None}


def last_run_status() -> Dict[str, Any]:
    return dict(_last_run)


async def run_ingest(full: bool = False) -> Dict[str, Any]:
    if _ingest_lock.locked():
        return {"error": "ingest already running", "status": last_run_status()}

    async with _ingest_lock:
        _last_run["running"] = True
        _last_run["started_at"] = int(time.time())
        _last_run["finished_at"] = None
        _last_run["stats"] = None

        settings.data_dir.mkdir(parents=True, exist_ok=True)
        state = StateStore(settings.state_file)

        seen_urls: set[str] = set()
        ingest_stats = {"new": 0, "updated": 0, "unchanged": 0, "chunks": 0, "failed": 0}

        async def handle(res: FetchResult, depth: int, is_seed_html: bool) -> None:
            url = res.final_url
            if url in seen_urls:
                return
            seen_urls.add(url)

            h = content_hash(res.content)
            prev = state.get(url)
            if not full and prev and prev.get("hash") == h:
                ingest_stats["unchanged"] += 1
                return

            doc = extract(res.content, res.content_type, url)
            if not doc or not doc.text.strip():
                ingest_stats["failed"] += 1
                return

            chunks = []
            for ch in chunk_text(doc.text):
                chunks.append(
                    {
                        "text": ch.text,
                        "title": doc.title,
                        "page_start": ch.page_start,
                        "page_end": ch.page_end,
                        "content_type": res.content_type.split(";")[0].strip() if res.content_type else None,
                        "indexed_at": int(time.time()),
                        "is_external": not is_seed_html and depth > 0,
                    }
                )

            if not chunks:
                ingest_stats["failed"] += 1
                return

            try:
                # Offload sync embedding/Chroma writes to a worker thread.
                added = await asyncio.to_thread(add_document, url, chunks)
            except Exception as e:
                print(f"[ingest] failed to index {url}: {e}")
                ingest_stats["failed"] += 1
                return

            state.set(url, h, res.etag)
            ingest_stats["chunks"] += added
            if prev:
                ingest_stats["updated"] += 1
            else:
                ingest_stats["new"] += 1

        def progress(url: str, stats: dict) -> None:
            if stats["fetched"] % 25 == 0:
                print(f"[ingest] fetched={stats['fetched']} extracted={stats['extracted']}")

        crawl_stats = await crawl(
            seed_urls=settings.seed_urls,
            seed_domains=settings.seed_domains,
            on_doc=handle,
            progress=progress,
        )

        # Prune URLs that disappeared from the crawl
        pruned = 0
        for url in list(state.all_urls()):
            if url not in seen_urls:
                try:
                    await asyncio.to_thread(delete_document, url)
                    state.remove(url)
                    pruned += 1
                except Exception:
                    pass

        state.save()

        _last_run["running"] = False
        _last_run["finished_at"] = int(time.time())
        _last_run["stats"] = {**crawl_stats, **ingest_stats, "pruned": pruned, "full": full}
        return _last_run["stats"]
