from __future__ import annotations

import pytest

from playground.model_client import (
    DASHSCOPE_DEFAULT_BASE_URL,
    build_json_client,
    dashscope_openai_client_kwargs,
)
from playground.openai_client import OpenAIChatClient
from playground.user_sim.tool_client import OpenAIToolStepClient, build_tool_step_client


class _FakeOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.chat = object()


def test_dashscope_openai_client_kwargs_reads_env(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-dashscope-test")
    monkeypatch.delenv("DASHSCOPE_API_BASE", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)

    kwargs = dashscope_openai_client_kwargs("dashscope/qwen3.7-max")
    assert kwargs == {
        "model": "qwen3.7-max",
        "api_key": "sk-dashscope-test",
        "base_url": DASHSCOPE_DEFAULT_BASE_URL,
    }


def test_build_json_client_routes_dashscope_to_openai_compatible(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-dashscope-test")
    created: list[dict[str, str]] = []

    def fake_openai(**kwargs):
        created.append(kwargs)
        return _FakeOpenAI(**kwargs)

    monkeypatch.setattr("openai.OpenAI", fake_openai)

    client = build_json_client("dashscope/qwen3.6-plus-2026-04-02")
    assert isinstance(client, OpenAIChatClient)
    assert client.model == "qwen3.6-plus-2026-04-02"
    assert created == [
        {
            "api_key": "sk-dashscope-test",
            "base_url": DASHSCOPE_DEFAULT_BASE_URL,
        }
    ]


def test_build_tool_step_client_routes_dashscope(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-dashscope-test")
    created: list[dict[str, str]] = []

    def fake_openai(**kwargs):
        created.append(kwargs)
        return _FakeOpenAI(**kwargs)

    monkeypatch.setattr("openai.OpenAI", fake_openai)

    client = build_tool_step_client("dashscope/deepseek-v4-pro")
    assert isinstance(client, OpenAIToolStepClient)
    assert client.model == "deepseek-v4-pro"
    assert created == [
        {
            "api_key": "sk-dashscope-test",
            "base_url": DASHSCOPE_DEFAULT_BASE_URL,
        }
    ]


def test_build_tool_step_client_routes_local_qwen_to_local_openai_endpoint(monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://local-qwen.test/v1")
    monkeypatch.setenv("LOCAL_LLM_AUTH_HEADER", "Basic local-secret")
    monkeypatch.setenv("LOCAL_LLM_MODEL", "Qwen3-14B")
    monkeypatch.setenv("LOCAL_LLM_ENABLE_THINKING", "false")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    created: list[dict[str, object]] = []

    def fake_openai(**kwargs):
        created.append(kwargs)
        return _FakeOpenAI(**kwargs)

    monkeypatch.setattr("openai.OpenAI", fake_openai)

    client = build_tool_step_client("local/qwen3-14b")

    assert isinstance(client, OpenAIToolStepClient)
    assert client.model == "Qwen3-14B"
    assert client.extra_body == {"chat_template_kwargs": {"enable_thinking": False}}
    assert created == [
        {
            "api_key": "Basic local-secret",
            "base_url": "http://local-qwen.test/v1",
            "default_headers": {"Authorization": "Basic local-secret"},
        }
    ]


def test_local_qwen_tool_client_uses_json_actions_without_native_tool_choice():
    captured: list[dict[str, object]] = []

    class _Completions:
        def create(self, **kwargs):
            captured.append(kwargs)
            message = type("Message", (), {"content": '{"action":"send_message","message":"I need a simple meal plan."}', "tool_calls": None})()
            choice = type("Choice", (), {"message": message})()
            usage = type("Usage", (), {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})()
            return type("Completion", (), {"choices": [choice], "usage": usage})()

    fake_client = type(
        "Client",
        (),
        {"chat": type("Chat", (), {"completions": _Completions()})()},
    )()
    client = OpenAIToolStepClient(
        "Qwen3-14B", client=fake_client, provider="local", native_tools=False
    )

    calls = client.complete_with_tools([{"role": "system", "content": "persona"}])

    assert calls[0].name == "send_message"
    assert calls[0].arguments == {"message": "I need a simple meal plan."}
    assert "tools" not in captured[0]
    assert "tool_choice" not in captured[0]
    assert captured[0]["response_format"] == {"type": "json_object"}


def test_build_json_client_requires_dashscope_key(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DASHSCOPE_API_KEY"):
        build_json_client("dashscope/qwen-plus")
