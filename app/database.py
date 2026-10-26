from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, path: str | Path, schema_path: str | Path | None = None) -> None:
        self.path = Path(path)
        self.schema_path = Path(schema_path) if schema_path else Path(__file__).parents[1] / "schema.sql"

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(self.schema_path.read_text(encoding="utf-8"))

    def get_settings(self) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM settings WHERE id = 1").fetchone()
        if row is None:
            raise RuntimeError("settings table has not been initialized")
        result = dict(row)
        result["topics"] = json.loads(result.pop("topics_json"))
        result["keywords"] = json.loads(result.pop("keywords_json"))
        result["push_enabled"] = bool(result["push_enabled"])
        return result

    def save_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE settings
                SET identity = ?, topics_json = ?, keywords_json = ?, timezone = ?,
                    push_time = ?, push_enabled = ?, updated_at = ?
                WHERE id = 1
                """,
                (
                    settings["identity"],
                    json.dumps(settings["topics"], ensure_ascii=False),
                    json.dumps(settings["keywords"], ensure_ascii=False),
                    settings["timezone"],
                    settings["push_time"],
                    int(settings["push_enabled"]),
                    _now_iso(),
                ),
            )
        return self.get_settings()

    def create_digest(self, trigger_type: str, local_date: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO digests (
                    trigger_type, local_date, status, push_status, created_at
                ) VALUES (?, ?, 'running', 'pending', ?)
                """,
                (trigger_type, local_date, _now_iso()),
            )
            return int(cursor.lastrowid)

    def complete_digest(
        self,
        digest_id: int,
        content_md: str,
        trace: list[dict[str, Any]],
        push_status: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE digests
                SET content_md = ?, trace_json = ?, status = 'completed',
                    push_status = ?, error_message = NULL, completed_at = ?
                WHERE id = ?
                """,
                (
                    content_md,
                    json.dumps(trace, ensure_ascii=False),
                    push_status,
                    _now_iso(),
                    digest_id,
                ),
            )

    def fail_digest(
        self,
        digest_id: int,
        error_message: str,
        trace: list[dict[str, Any]],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE digests
                SET trace_json = ?, status = 'failed', push_status = 'skipped',
                    error_message = ?, completed_at = ?
                WHERE id = ?
                """,
                (json.dumps(trace, ensure_ascii=False), error_message, _now_iso(), digest_id),
            )

    def get_digest(self, digest_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM digests WHERE id = ?", (digest_id,)).fetchone()
        return dict(row) if row else None

    def list_digests(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM digests ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]
