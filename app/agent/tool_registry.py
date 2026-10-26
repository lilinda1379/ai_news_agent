from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.tools.filesystem import FilesystemTools
from app.tools.news import NewsSearchTool


class ListDirInput(BaseModel):
    path: str = Field(description="Path relative to the tool workspace")


class ReadFileInput(BaseModel):
    path: str = Field(description="File path relative to the tool workspace")


class SearchContentInput(BaseModel):
    keyword: str = Field(min_length=1, description="Text to find")
    dir: str = Field(description="Directory relative to the tool workspace")


class WriteFileInput(BaseModel):
    path: str = Field(description="File path relative to the tool workspace")
    content: str = Field(description="UTF-8 text to write")


class BashInput(BaseModel):
    command: str = Field(min_length=1, description="Safe allowlisted command")


class SearchNewsInput(BaseModel):
    query: str = Field(min_length=1, description="AI news search query")
    limit: int = Field(default=10, ge=1, le=20)


ToolHandler = Callable[..., dict[str, Any]]


class ToolRegistry:
    def __init__(self, filesystem: FilesystemTools, news: NewsSearchTool) -> None:
        self._tools: list[tuple[str, str, type[BaseModel], ToolHandler]] = [
            ("list_dir", "List files and directories in the workspace.", ListDirInput, filesystem.list_dir),
            ("read_file", "Read a UTF-8 text file from the workspace.", ReadFileInput, filesystem.read_file),
            (
                "search_content",
                "Search workspace text files for a keyword.",
                SearchContentInput,
                filesystem.search_content,
            ),
            ("write_file", "Write a UTF-8 text file inside the workspace.", WriteFileInput, filesystem.write_file),
            ("bash", "Run a safe allowlisted shell-like command.", BashInput, filesystem.bash),
            ("search_news", "Search current AI news using Google News RSS.", SearchNewsInput, news.search_news),
        ]
        self._by_name = {name: (model, handler) for name, _, model, handler in self._tools}

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": model.model_json_schema(),
                },
            }
            for name, description, model, _ in self._tools
        ]

    def execute(self, name: str, arguments: str | dict[str, Any]) -> dict[str, Any]:
        selected = self._by_name.get(name)
        if selected is None:
            return {"ok": False, "data": None, "error": f"unknown tool: {name}"}
        model, handler = selected
        try:
            raw_arguments = json.loads(arguments) if isinstance(arguments, str) else arguments
            validated = model.model_validate(raw_arguments)
        except (json.JSONDecodeError, TypeError, ValidationError) as exc:
            return {"ok": False, "data": None, "error": f"invalid arguments: {exc}"}
        return handler(**validated.model_dump())

