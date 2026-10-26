from __future__ import annotations

from collections.abc import Callable
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger


class DigestScheduler:
    def __init__(
        self,
        job: Callable[[], Any],
        backend: BackgroundScheduler | None = None,
    ) -> None:
        self.job = job
        self.backend = backend or BackgroundScheduler()

    def configure(self, settings: dict[str, Any]) -> None:
        hour_text, minute_text = settings["push_time"].split(":", maxsplit=1)
        trigger = CronTrigger(
            hour=int(hour_text),
            minute=int(minute_text),
            timezone=ZoneInfo(settings["timezone"]),
        )
        if self.backend.get_job("daily-digest") is not None:
            self.backend.remove_job("daily-digest")
        self.backend.add_job(
            self.job,
            trigger=trigger,
            id="daily-digest",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )

    def start(self) -> None:
        if not self.backend.running:
            self.backend.start()

    def shutdown(self) -> None:
        if self.backend.running:
            self.backend.shutdown(wait=False)

