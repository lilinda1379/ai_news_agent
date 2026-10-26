from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

from openai import OpenAI


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ModelResponse:
    content: str | None
    tool_calls: list[ToolCall]


@dataclass(frozen=True)
class AgentRunResult:
    content: str
    trace: list[dict[str, Any]]


class AgentLoopError(RuntimeError):
    def __init__(self, message: str, trace: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.trace = trace or []


class Gateway(Protocol):
    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelResponse: ...


class Registry(Protocol):
    def schemas(self) -> list[dict[str, Any]]: ...

    def execute(self, name: str, arguments: str | dict[str, Any]) -> dict[str, Any]: ...


class OpenAIChatGateway:
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelResponse:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.2,
        )
        message = response.choices[0].message
        tool_calls = [
            ToolCall(
                id=call.id,
                name=call.function.name,
                arguments=call.function.arguments,
            )
            for call in (message.tool_calls or [])
        ]
        return ModelResponse(content=message.content, tool_calls=tool_calls)


class AgentRunner:
    def __init__(self, gateway: Gateway, registry: Registry, max_steps: int = 6) -> None:
        self.gateway = gateway
        self.registry = registry
        self.max_steps = max_steps

    def run(self, system_prompt: str, task: str) -> AgentRunResult:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]
        trace: list[dict[str, Any]] = []
        seen_calls: set[str] = set()
        searched_news = False

        for step in range(1, self.max_steps + 1):
            response = self.gateway.complete(messages, self.registry.schemas())
            trace.append(
                {
                    "type": "model",
                    "step": step,
                    "content": response.content,
                    "tool_calls": [
                        {"id": call.id, "name": call.name, "arguments": call.arguments}
                        for call in response.tool_calls
                    ],
                }
            )

            if not response.tool_calls:
                content = (response.content or "").strip()
                if not searched_news:
                    raise AgentLoopError("search_news was not called", trace)
                if not re.search(r"https?://", content):
                    raise AgentLoopError("digest has no source link", trace)
                return AgentRunResult(content=content, trace=trace)

            messages.append(
                {
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {"name": call.name, "arguments": call.arguments},
                        }
                        for call in response.tool_calls
                    ],
                }
            )

            for call in response.tool_calls:
                signature = f"{call.name}:{self._canonical_arguments(call.arguments)}"
                started = time.perf_counter()
                if signature in seen_calls:
                    result = {"ok": False, "data": None, "error": "duplicate tool call"}
                else:
                    seen_calls.add(signature)
                    result = self.registry.execute(call.name, call.arguments)
                    searched_news = searched_news or call.name == "search_news" and bool(result.get("ok"))
                duration_ms = round((time.perf_counter() - started) * 1000, 2)
                trace.append(
                    {
                        "type": "tool",
                        "step": step,
                        "tool_call_id": call.id,
                        "tool": call.name,
                        "arguments": self._display_arguments(call.arguments),
                        "result": result,
                        "duration_ms": duration_ms,
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        raise AgentLoopError("maximum agent steps exceeded", trace)

    @staticmethod
    def _canonical_arguments(arguments: str) -> str:
        try:
            return json.dumps(json.loads(arguments), ensure_ascii=False, sort_keys=True)
        except json.JSONDecodeError:
            return arguments

    @staticmethod
    def _display_arguments(arguments: str) -> dict[str, Any] | str:
        try:
            return json.loads(arguments)
        except json.JSONDecodeError:
            return arguments
