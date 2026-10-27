from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any
from zoneinfo import ZoneInfo
from datetime import datetime

from app.agent.loop import AgentLoopError, AgentRunner
from app.agent.prompts import SYSTEM_PROMPT, build_digest_task
from app.database import Database


PushFunction = Callable[[str], str]


class DigestService:
    def __init__(
        self,
        database: Database,
        runner: AgentRunner,
        push: PushFunction | None = None,
    ) -> None:
        self.database = database
        self.runner = runner
        self.push = push
        # 调度任务和手动点击可能同时触发；同一时刻只允许跑一个 Agent
        self._run_lock = threading.Lock()

    def generate(self, trigger_type: str = "manual") -> dict[str, Any]:
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("generation already running")
        try:
            return self._generate_locked(trigger_type)
        finally:
            self._run_lock.release()

    def _generate_locked(self, trigger_type: str) -> dict[str, Any]:
        settings = self.database.get_settings()
        local_date = datetime.now(ZoneInfo(settings["timezone"])).date().isoformat()
        digest_id = self.database.create_digest(trigger_type, local_date)
        trace: list[dict[str, Any]] = []
        try:
            result = self.runner.run(
                SYSTEM_PROMPT,
                build_digest_task(settings, local_date),
            )
            trace = result.trace
            push_status = "skipped"
            if settings["push_enabled"] and self.push is not None:
                push_status = self.push(result.content)
            self.database.complete_digest(
                digest_id,
                content_md=result.content,
                trace=trace,
                push_status=push_status,
            )
            return self.database.get_digest(digest_id)
        except AgentLoopError as exc:
            self.database.fail_digest(digest_id, str(exc), exc.trace)
            raise
        except Exception as exc:
            self.database.fail_digest(digest_id, str(exc), trace)
            raise

