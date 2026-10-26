import json
from types import SimpleNamespace

import pytest

from app.agent.loop import AgentLoopError, AgentRunner, ModelResponse, ToolCall


class FakeGateway:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def complete(self, messages, tools):
        self.requests.append({"messages": list(messages), "tools": tools})
        return self.responses.pop(0)


class FakeRegistry:
    def __init__(self):
        self.calls = []

    def schemas(self):
        return [{"type": "function", "function": {"name": "search_news"}}]

    def execute(self, name, arguments):
        self.calls.append((name, arguments))
        return {
            "ok": True,
            "data": {
                "items": [
                    {
                        "title": "Agent update",
                        "url": "https://example.com/agent",
                        "summary": "Details",
                    }
                ]
            },
            "error": None,
        }


def tool_response(call_id="call-1", arguments='{"query":"AI Agent"}'):
    return ModelResponse(
        content=None,
        tool_calls=[ToolCall(id=call_id, name="search_news", arguments=arguments)],
    )


def test_agent_executes_model_selected_tool_then_stops_on_final_answer():
    gateway = FakeGateway(
        [
            tool_response(),
            ModelResponse(
                content="# 简报\n\n[Agent update](https://example.com/agent)",
                tool_calls=[],
            ),
        ]
    )
    registry = FakeRegistry()

    result = AgentRunner(gateway, registry, max_steps=6).run("system", "prepare digest")

    assert result.content.startswith("# 简报")
    assert registry.calls == [("search_news", '{"query":"AI Agent"}')]
    tool_message = gateway.requests[1]["messages"][-1]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call-1"
    assert json.loads(tool_message["content"])["ok"] is True
    assert [event["type"] for event in result.trace] == ["model", "tool", "model"]


def test_agent_does_not_execute_duplicate_tool_call_twice():
    gateway = FakeGateway(
        [
            tool_response("call-1"),
            tool_response("call-2"),
            ModelResponse(content="[source](https://example.com/agent)", tool_calls=[]),
        ]
    )
    registry = FakeRegistry()

    result = AgentRunner(gateway, registry, max_steps=6).run("system", "prepare digest")

    assert len(registry.calls) == 1
    duplicate_event = [event for event in result.trace if event["type"] == "tool"][1]
    assert duplicate_event["result"]["error"] == "duplicate tool call"


def test_agent_fails_after_maximum_number_of_model_steps():
    gateway = FakeGateway([tool_response(f"call-{index}", f'{{"query":"AI {index}"}}') for index in range(3)])
    registry = FakeRegistry()

    with pytest.raises(AgentLoopError, match="maximum agent steps exceeded") as error:
        AgentRunner(gateway, registry, max_steps=3).run("system", "prepare digest")

    assert len(error.value.trace) == 6


def test_agent_rejects_final_answer_without_news_search():
    gateway = FakeGateway(
        [ModelResponse(content="[made up](https://example.com/fake)", tool_calls=[])]
    )

    with pytest.raises(AgentLoopError, match="search_news was not called"):
        AgentRunner(gateway, FakeRegistry()).run("system", "prepare digest")


def test_agent_rejects_final_answer_without_source_link():
    gateway = FakeGateway(
        [tool_response(), ModelResponse(content="A digest without links", tool_calls=[])]
    )

    with pytest.raises(AgentLoopError, match="digest has no source link"):
        AgentRunner(gateway, FakeRegistry()).run("system", "prepare digest")
