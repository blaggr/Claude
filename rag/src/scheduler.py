from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import settings
from .ingest import run_ingest

log = logging.getLogger("rag.scheduler")


def start_scheduler() -> AsyncIOScheduler | None:
    if not settings.enable_scheduler:
        log.info("Scheduler disabled.")
        return None
    parts = settings.reindex_cron.split()
    if len(parts) != 5:
        log.warning("Invalid REINDEX_CRON %r; scheduler not started.", settings.reindex_cron)
        return None
    minute, hour, day, month, dow = parts
    trigger = CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=dow)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(_run_job, trigger=trigger, id="weekly_reindex", replace_existing=True)
    scheduler.start()
    log.info("Scheduler started with cron %r", settings.reindex_cron)
    return scheduler


async def _run_job() -> None:
    log.info("Running scheduled reindex…")
    try:
        stats = await run_ingest(full=False)
        log.info("Scheduled reindex complete: %s", stats)
    except Exception as e:
        log.exception("Scheduled reindex failed: %s", e)
