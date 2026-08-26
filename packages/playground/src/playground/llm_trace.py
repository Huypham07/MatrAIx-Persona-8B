"""Append-only, secret-safe trace records for persona LLM calls."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any, Mapping
import uuid


_SECRET_KEYS = {
    "authorization",
    "proxy-authorization",
    "api_key",
    "apikey",
    "x-api-key",
    "cookie",
    "set-cookie",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): (
                "[REDACTED]"
                if str(key).strip().lower() in _SECRET_KEYS
                else _redact(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def _usage_payload(usage: Any) -> dict[str, Any] | None:
    if usage is None:
        return None
    raw = usage.to_dict() if hasattr(usage, "to_dict") else usage
    if not isinstance(raw, Mapping):
        return None
    aliases = {
        "n_input_tokens": "inputTokens",
        "n_output_tokens": "outputTokens",
        "n_cache_tokens": "cacheTokens",
        "cost_usd": "costUsd",
        "request_id": "requestId",
        "cost_source": "costSource",
    }
    return {
        aliases.get(str(key), str(key)): item
        for key, item in raw.items()
        if item is not None
    }


class LlmTraceWriter:
    """Write one complete JSON object per model attempt."""

    def __init__(
        self,
        path: str | Path,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self.path = Path(path)
        self.metadata = dict(metadata or {})
        self._lock = threading.Lock()

    def record(
        self,
        *,
        model: str,
        provider: str,
        messages: list[dict[str, Any]],
        raw_output: Any = None,
        parsed_output: Any = None,
        usage: Any = None,
        finish_reason: str | None = None,
        error: BaseException | Mapping[str, Any] | None = None,
        step: str = "completion",
        started_at: str | None = None,
        duration_ms: float | None = None,
        attempt: int = 1,
    ) -> None:
        if isinstance(error, BaseException):
            error_payload: dict[str, Any] | None = {
                "type": type(error).__name__,
                "message": str(error),
            }
        elif isinstance(error, Mapping):
            error_payload = dict(error)
        else:
            error_payload = None
        payload = {
            "schemaVersion": "1.0",
            "callId": str(uuid.uuid4()),
            "timestamp": started_at or _utc_now(),
            "step": step,
            "attempt": int(attempt),
            "model": model,
            "provider": provider,
            "messages": messages,
            "rawOutput": raw_output,
            "parsedOutput": parsed_output,
            "usage": _usage_payload(usage),
            "finishReason": finish_reason,
            "durationMs": duration_ms,
            "error": error_payload,
            **self.metadata,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(_redact(payload), ensure_ascii=False, default=str) + "\n"
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
