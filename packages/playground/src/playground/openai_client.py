from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, Optional, Protocol

from playground.llm_usage import JsonCompletion, usage_from_openai_completion

_FENCE = re.compile(r"```(?:json)?\s*(?P<body>\{.*\})\s*```", re.DOTALL)
DEFAULT_REQUEST_TIMEOUT_SECONDS = 180.0


def coerce_json(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    if "<think>" in text:
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = _FENCE.search(text)
    if match:
        try:
            return json.loads(match.group("body"))
        except json.JSONDecodeError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError("could not parse JSON from model output: {!r}".format(text[:200]))


def openai_model_supports_custom_temperature(model: str) -> bool:
    """Whether Chat Completions / Messages accepts a non-default ``temperature``.

    GPT-5 family models currently only allow the API default (1); sending
    ``0.1`` / ``0.7`` returns HTTP 400. Claude Opus 4.7+ (and Bedrock Opus)
    similarly reject an explicit non-default temperature.
    """
    lowered = (model or "").strip().lower()
    bare = lowered.rsplit("/", 1)[-1] if "/" in lowered else lowered
    if bare.startswith("gpt-5"):
        return False
    opus = re.search(r"opus-4-(\d+)", lowered)
    if opus is not None and int(opus.group(1)) >= 7:
        return False
    if "bedrock" in lowered and "opus" in lowered:
        return False
    return True


class ChatClient(Protocol):
    def complete_json(self, system: str, user: str) -> Dict[str, Any]: ...


class OpenAIChatClient:
    """OpenAI v1 client (`from openai import OpenAI`) using JSON response mode."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        client: Optional[Any] = None,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_headers: Optional[Dict[str, str]] = None,
        extra_body: Optional[Dict[str, Any]] = None,
        temperature: float = 0.7,
        timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        provider: str = "openai",
        trace_writer: Any = None,
        trace_step: str = "json_completion",
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self.provider = provider
        self.extra_body = extra_body or {}
        self.trace_writer = trace_writer
        self.trace_step = trace_step
        if client is None:
            from openai import OpenAI  # lazy: tests inject a fake

            client_kwargs: Dict[str, Any] = {
                "api_key": (api_key or os.environ.get("OPENAI_API_KEY") or "dummy").strip() or "dummy"
            }
            if base_url:
                client_kwargs["base_url"] = base_url
            if default_headers:
                client_kwargs["default_headers"] = default_headers
            client = OpenAI(**client_kwargs)
        self._client = client

    def complete_json(self, system: str, user: str) -> Dict[str, Any]:
        return self.complete_json_with_usage(system, user).data

    def complete_json_with_usage(self, system: str, user: str) -> JsonCompletion:
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "timeout": self.timeout_seconds,
        }
        if self.extra_body:
            kwargs["extra_body"] = self.extra_body
        if openai_model_supports_custom_temperature(self.model):
            kwargs["temperature"] = self.temperature
        started = time.monotonic()
        raw_output = None
        usage = None
        completion = None
        try:
            completion = self._client.chat.completions.create(**kwargs)
            raw_output = completion.choices[0].message.content
            data = coerce_json(raw_output)
            usage = usage_from_openai_completion(
                completion, model=self.model, provider=self.provider
            )
        except Exception as exc:
            if self.trace_writer is not None:
                self.trace_writer.record(
                    model=self.model,
                    provider=self.provider,
                    messages=list(kwargs["messages"]),
                    raw_output=raw_output,
                    parsed_output=None,
                    usage=usage,
                    finish_reason=(
                        getattr(completion.choices[0], "finish_reason", None)
                        if completion is not None
                        else None
                    ),
                    error=exc,
                    step=self.trace_step,
                    duration_ms=round((time.monotonic() - started) * 1000, 3),
                )
            raise
        if self.trace_writer is not None:
            self.trace_writer.record(
                model=self.model,
                provider=self.provider,
                messages=list(kwargs["messages"]),
                raw_output=raw_output,
                parsed_output=data,
                usage=usage,
                finish_reason=getattr(completion.choices[0], "finish_reason", None),
                step=self.trace_step,
                duration_ms=round((time.monotonic() - started) * 1000, 3),
            )
        return JsonCompletion(data=data, usage=usage)
