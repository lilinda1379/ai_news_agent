import json

from app.database import Database


def test_database_initializes_singleton_settings_and_persists_updates(tmp_path):
    db = Database(tmp_path / "agent.db")
    db.initialize()

    initial = db.get_settings()
    assert initial["identity"] == "AI 从业者"
    assert initial["topics"] == ["AI Agent"]
    assert initial["timezone"] == "Asia/Shanghai"

    saved = db.save_settings(
        {
            "identity": "AI 产品经理",
            "topics": ["Agent", "多模态"],
            "keywords": ["OpenAI"],
            "timezone": "Asia/Shanghai",
            "push_time": "08:30",
            "push_enabled": True,
        }
    )

    assert saved["identity"] == "AI 产品经理"
    assert saved["topics"] == ["Agent", "多模态"]
    assert saved["push_enabled"] is True


def test_digest_lifecycle_records_trace_and_push_status(tmp_path):
    db = Database(tmp_path / "agent.db")
    db.initialize()

    digest_id = db.create_digest(trigger_type="manual", local_date="2026-10-26")
    db.complete_digest(
        digest_id,
        content_md="# 今日简报\n\n[来源](https://example.com)",
        trace=[{"step": 1, "tool": "search_news"}],
        push_status="sent",
    )

    digest = db.get_digest(digest_id)
    assert digest["status"] == "completed"
    assert digest["push_status"] == "sent"
    assert json.loads(digest["trace_json"])[0]["tool"] == "search_news"


def test_failed_digest_keeps_error_for_history(tmp_path):
    db = Database(tmp_path / "agent.db")
    db.initialize()

    digest_id = db.create_digest(trigger_type="scheduled", local_date="2026-10-26")
    db.fail_digest(digest_id, "model unavailable", trace=[])

    digest = db.get_digest(digest_id)
    assert digest["status"] == "failed"
    assert digest["error_message"] == "model unavailable"


def test_database_enables_wal_journal(tmp_path):
    db = Database(tmp_path / "agent.db")
    db.initialize()

    with db._connect() as connection:
        mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

    assert mode.lower() == "wal"
