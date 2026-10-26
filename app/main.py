from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

from app.agent.loop import AgentRunner, ModelResponse, OpenAIChatGateway
from app.agent.tool_registry import ToolRegistry
from app.config import AppConfig
from app.database import Database
from app.services.digest import DigestService
from app.services.feishu import FeishuPush
from app.services.scheduler import DigestScheduler
from app.tools.filesystem import FilesystemTools
from app.tools.news import NewsSearchTool


APP_DIR = Path(__file__).parent


class MissingGateway:
    def complete(self, messages, tools) -> ModelResponse:
        raise RuntimeError("OPENAI_API_KEY is not configured")


class SettingsPayload(BaseModel):
    identity: str = Field(min_length=1, max_length=100)
    topics: list[str] = Field(min_length=1, max_length=10)
    keywords: list[str] = Field(default_factory=list, max_length=20)
    timezone: str = "Asia/Shanghai"
    push_time: str = Field(default="09:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    push_enabled: bool = False

    @field_validator("identity")
    @classmethod
    def clean_identity(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("identity is required")
        return value

    @field_validator("topics", "keywords")
    @classmethod
    def clean_terms(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if not cleaned and values:
            raise ValueError("terms cannot contain only whitespace")
        return cleaned

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("unknown timezone") from exc
        return value


def create_app(
    config: AppConfig | None = None,
    *,
    gateway: Any | None = None,
    news_fetch=None,
    push=None,
    scheduler=None,
) -> FastAPI:
    config = config or AppConfig.from_env()
    database = Database(config.database_path)
    filesystem = FilesystemTools(config.workspace_root)
    news = NewsSearchTool(fetch=news_fetch)
    registry = ToolRegistry(filesystem, news)
    if gateway is None:
        gateway = (
            OpenAIChatGateway(config.openai_api_key, config.openai_base_url, config.openai_model)
            if config.openai_api_key
            else MissingGateway()
        )
    runner = AgentRunner(gateway, registry)
    push_function = push or FeishuPush(config.feishu_webhook_url).send
    digest_service = DigestService(database, runner, push=push_function)
    digest_scheduler = scheduler or DigestScheduler(
        lambda: digest_service.generate("scheduled")
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        database.initialize()
        digest_scheduler.configure(database.get_settings())
        digest_scheduler.start()
        try:
            yield
        finally:
            digest_scheduler.shutdown()

    application = FastAPI(title="每日 AI 新闻助手 Agent", lifespan=lifespan)
    application.state.database = database
    application.state.digest_service = digest_service
    application.state.digest_scheduler = digest_scheduler
    templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
    application.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

    @application.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "settings": database.get_settings(),
                "digests": database.list_digests(),
            },
        )

    @application.get("/health")
    def health() -> dict[str, str]:
        database.get_settings()
        return {"status": "ok"}

    @application.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        return database.get_settings()

    @application.put("/api/settings")
    def put_settings(payload: SettingsPayload) -> dict[str, Any]:
        saved = database.save_settings(payload.model_dump())
        digest_scheduler.configure(saved)
        return saved

    @application.post("/api/digests/generate", status_code=201)
    def generate_digest() -> dict[str, Any]:
        try:
            return digest_service.generate("manual")
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @application.get("/api/digests")
    def list_digests(limit: int = 20) -> list[dict[str, Any]]:
        return database.list_digests(max(1, min(limit, 100)))

    @application.get("/api/digests/{digest_id}")
    def get_digest(digest_id: int) -> dict[str, Any]:
        digest = database.get_digest(digest_id)
        if digest is None:
            raise HTTPException(status_code=404, detail="digest not found")
        return digest

    return application


app = create_app()

