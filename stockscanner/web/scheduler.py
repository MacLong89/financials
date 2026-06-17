from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from stockscanner.config import ScannerConfig
from stockscanner.web.service import run_and_store

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def start_scheduler(config: ScannerConfig) -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    hour = int(config.section("web").get("schedule_hour", 7))
    minute = int(config.section("web").get("schedule_minute", 30))
    tz = config.section("web").get("timezone", "America/Denver")
    send_alert = bool(config.section("web").get("schedule_alert", True))
    fast = bool(config.section("web").get("schedule_fast", True))

    scheduler = BackgroundScheduler(timezone=tz)

    def _job() -> None:
        logger.info("Scheduled scan starting")
        try:
            run_and_store(config, fast=fast, source="scheduled", send_alert=send_alert)
            logger.info("Scheduled scan complete")
        except Exception:
            logger.exception("Scheduled scan failed")

    scheduler.add_job(
        _job,
        CronTrigger(
            day_of_week="mon-fri",
            hour=hour,
            minute=minute,
            timezone=tz,
        ),
        id="morning_scan",
        replace_existing=True,
    )
    scheduler.start()
    _scheduler = scheduler
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
