import json

from app.agent.tool_registry import ToolRegistry
from app.tools.filesystem import FilesystemTools
from app.tools.news import NewsSearchTool


def test_registry_exposes_all_required_tools_and_executes_valid_call(tmp_path):
    registry = ToolRegistry(
        FilesystemTools(tmp_path),
        NewsSearchTool(fetch=lambda _: b"<rss><channel></channel></rss>"),
    )

    names = [schema["function"]["name"] for schema in registry.schemas()]
    result = registry.execute("write_file", json.dumps({"path": "a.txt", "content": "hello"}))

    assert names == [
        "list_dir",
        "read_file",
        "search_content",
        "write_file",
        "bash",
        "search_news",
    ]
    assert result["ok"] is True
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "hello"


def test_registry_returns_structured_error_for_bad_arguments(tmp_path):
    registry = ToolRegistry(FilesystemTools(tmp_path), NewsSearchTool(fetch=lambda _: b""))

    result = registry.execute("search_news", '{"limit": 5}')

    assert result["ok"] is False
    assert result["error"].startswith("invalid arguments:")


def test_registry_returns_structured_error_for_unknown_tool(tmp_path):
    registry = ToolRegistry(FilesystemTools(tmp_path), NewsSearchTool(fetch=lambda _: b""))

    result = registry.execute("delete_everything", "{}")

    assert result == {"ok": False, "data": None, "error": "unknown tool: delete_everything"}

