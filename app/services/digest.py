from __future__ import annotations

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

    def generate(self, trigger_type: str = "manual") -> dict[str, Any]:
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

