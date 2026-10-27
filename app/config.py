from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _env_int(name: str, default: int) -> int:
    """读正整数环境变量；空值/非法值回退默认，避免启动即崩。"""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


@dataclass(frozen=True)
class AppConfig:
    openai_api_key: str
    openai_base_url: str
    openai_model: str
    feishu_webhook_url: str
    database_path: Path
    workspace_root: Path
    app_timezone: str
    agent_max_steps: int = 10

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_dotenv()
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            feishu_webhook_url=os.getenv("FEISHU_WEBHOOK_URL", ""),
            database_path=Path(os.getenv("DATABASE_PATH", "data/ai_news_agent.db")),
            workspace_root=Path(os.getenv("WORKSPACE_ROOT", "data/workspace")),
            app_timezone=os.getenv("APP_TIMEZONE", "Asia/Shanghai"),
            agent_max_steps=_env_int("AGENT_MAX_STEPS", 10),
        )
