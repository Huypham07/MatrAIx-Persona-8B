from __future__ import annotations

import json

import pytest

from playground.llm_trace import LlmTraceWriter
from playground.openai_client import OpenAIChatClient


class _Message:
    def __init__(self, content: str):
        self.content = content


class _Choice:
    def __init__(self, content: str):
        self.message = _Message(content)
        self.finish_reason = "stop"


class _Usage:
    prompt_tokens = 7
    completion_tokens = 3
    prompt_tokens_details = None


class _Completion:
    def __init__(self, content: str):
        self.choices = [_Choice(content)]
        self.usage = _Usage()
        self.id = "trace-request"


class _Completions:
    def __init__(self, content: str):
        self.content = content

    def create(self, **_kwargs):
        return _Completion(self.content)


class _Client:
    def __init__(self, content: str):
        self.chat = type("Chat", (), {"completions": _Completions(content)})()


def _records(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_openai_client_traces_exact_messages_raw_and_parsed_output(tmp_path):
    path = tmp_path / "llm_calls.jsonl"
    trace = LlmTraceWriter(
        path,
        metadata={
            "jobId": "job",
            "trialId": "trial",
            "personaId": "0042",
            "segmentId": "careful",
            "expectedLanguage": "Spanish",
        },
    )
    client = OpenAIChatClient(
        model="Qwen3-14B",
        client=_Client('{"answer":"sí"}'),
        provider="local",
        trace_writer=trace,
    )

    assert client.complete_json("system exact", "user exact") == {"answer": "sí"}
    [record] = _records(path)
    assert record["messages"] == [
        {"role": "system", "content": "system exact"},
        {"role": "user", "content": "user exact"},
    ]
    assert record["rawOutput"] == '{"answer":"sí"}'
    assert record["parsedOutput"] == {"answer": "sí"}
    assert record["model"] == "Qwen3-14B"
    assert record["expectedLanguage"] == "Spanish"
    assert record["usage"]["inputTokens"] == 7
    assert record["finishReason"] == "stop"


def test_openai_client_traces_unparseable_raw_output_and_error(tmp_path):
    path = tmp_path / "llm_calls.jsonl"
    client = OpenAIChatClient(
        model="Qwen3-14B",
        client=_Client("not-json"),
        trace_writer=LlmTraceWriter(path),
    )

    with pytest.raises(ValueError):
        client.complete_json("system", "user")

    [record] = _records(path)
    assert record["rawOutput"] == "not-json"
    assert record["parsedOutput"] is None
    assert "could not parse JSON" in record["error"]["message"]


def test_trace_writer_redacts_secret_fields(tmp_path):
    path = tmp_path / "llm_calls.jsonl"
    writer = LlmTraceWriter(path)
    writer.record(
        model="m",
        provider="p",
        messages=[],
        raw_output="ok",
        parsed_output={"authorization": "Bearer secret", "answer": "safe"},
    )

    [record] = _records(path)
    assert record["parsedOutput"]["authorization"] == "[REDACTED]"
    assert record["parsedOutput"]["answer"] == "safe"
