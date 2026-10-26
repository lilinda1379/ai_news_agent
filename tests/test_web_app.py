from pathlib import Path

from fastapi.testclient import TestClient

from app.agent.loop import ModelResponse, ToolCall
from app.config import AppConfig
from app.main import create_app


RSS_XML = b"""<rss version="2.0"><channel><item>
<title>Agent Update</title><link>https://example.com/agent</link>
<description>Details</description><pubDate>Tue, 27 Oct 2026 01:00:00 GMT</pubDate>
<source>Example AI</source></item></channel></rss>"""


class FakeGateway:
    def __init__(self, responses):
        self.responses = list(responses)

    def complete(self, messages, tools):
        return self.responses.pop(0)


def make_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        openai_api_key="test-key",
        openai_base_url="https://llm.example/v1",
        openai_model="test-model",
        feishu_webhook_url="",
        database_path=tmp_path / "agent.db",
        workspace_root=tmp_path / "workspace",
        app_timezone="Asia/Shanghai",
    )


def successful_gateway():
    return FakeGateway(
        [
            ModelResponse(
                content=None,
                tool_calls=[
                    ToolCall("call-1", "search_news", '{"query":"AI Agent","limit":5}')
                ],
            ),
            ModelResponse(
                content="# 每日简报\n\n- [Agent Update](https://example.com/agent)",
                tool_calls=[],
            ),
        ]
    )


def test_settings_page_and_api_persist_valid_profile(tmp_path):
    app = create_app(make_config(tmp_path), gateway=successful_gateway(), news_fetch=lambda _: RSS_XML)

    with TestClient(app) as client:
        health = client.get("/health")
        response = client.put(
            "/api/settings",
            json={
                "identity": "AI 产品经理",
                "topics": ["Agent", "多模态"],
                "keywords": ["OpenAI"],
                "timezone": "Asia/Shanghai",
                "push_time": "08:30",
                "push_enabled": False,
            },
        )
        page = client.get("/")

    assert health.json() == {"status": "ok"}
    assert response.status_code == 200
    assert response.json()["identity"] == "AI 产品经理"
    assert "AI 产品经理" in page.text


def test_settings_api_rejects_unknown_timezone(tmp_path):
    app = create_app(make_config(tmp_path), gateway=successful_gateway(), news_fetch=lambda _: RSS_XML)

    with TestClient(app) as client:
        response = client.put(
            "/api/settings",
            json={
                "identity": "Engineer",
                "topics": ["Agent"],
                "keywords": [],
                "timezone": "Mars/Olympus",
                "push_time": "09:00",
                "push_enabled": False,
            },
        )

    assert response.status_code == 422


def test_manual_generation_persists_digest_and_trace(tmp_path):
    app = create_app(make_config(tmp_path), gateway=successful_gateway(), news_fetch=lambda _: RSS_XML)

    with TestClient(app) as client:
        response = client.post("/api/digests/generate")
        history = client.get("/api/digests")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["push_status"] == "skipped"
    assert "https://example.com/agent" in body["content_md"]
    assert history.json()[0]["id"] == body["id"]
    assert '"tool": "search_news"' in body["trace_json"]


def test_failed_generation_remains_visible_in_history(tmp_path):
    gateway = FakeGateway([ModelResponse(content="No grounded news", tool_calls=[])])
    app = create_app(make_config(tmp_path), gateway=gateway, news_fetch=lambda _: RSS_XML)

    with TestClient(app) as client:
        response = client.post("/api/digests/generate")
        history = client.get("/api/digests")

    assert response.status_code == 502
    assert history.json()[0]["status"] == "failed"
    assert history.json()[0]["error_message"] == "search_news was not called"
