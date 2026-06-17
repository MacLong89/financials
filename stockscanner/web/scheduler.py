from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from stockscanner.config import ScannerConfig
from stockscanner.web.service import run_morning_routine

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def start_scheduler(config: ScannerConfig) -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    web_cfg = config.section("web")
    hour = int(web_cfg.get("schedule_hour", 7))
    minute = int(web_cfg.get("schedule_minute", 30))
    tz = web_cfg.get("timezone", "America/Denver")
    send_alert = bool(web_cfg.get("schedule_alert", True))

    scheduler = BackgroundScheduler(timezone=tz)

    def _job() -> None:
        logger.info("Scheduled morning routine starting")
        try:
            run_morning_routine(config, send_alert=send_alert)
            logger.info("Scheduled morning routine complete")
        except Exception:
            logger.exception("Scheduled morning routine failed")

    scheduler.add_job(
        _job,
        CronTrigger(
            day_of_week="mon-fri",
            hour=hour,
            minute=minute,
            timezone=tz,
        ),
        id="morning_routine",
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
