import threading
import time

import pytest

from app.database import Database
from app.services.digest import DigestService


class SlowRunner:
    """模拟一次耗时 300ms 的 Agent 运行。"""

    def run(self, system_prompt: str, task: str):
        time.sleep(0.3)
        result = type("Result", (), {})()
        result.content = "# 简报\n\n[来源](https://example.com)"
        result.trace = []
        return result


def test_second_generate_is_rejected_while_one_is_running(tmp_path):
    database = Database(tmp_path / "agent.db")
    database.initialize()
    service = DigestService(database, SlowRunner(), push=None)

    thread = threading.Thread(target=service.generate, kwargs={"trigger_type": "manual"})
    thread.start()
    time.sleep(0.05)

    with pytest.raises(RuntimeError, match="already running"):
        service.generate("manual")

    thread.join()
