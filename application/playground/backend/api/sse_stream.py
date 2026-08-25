"""Disconnect-aware SSE encoding for durable Harbor job journals."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

from playground.harbor.trial_events import JOB_EVENTS_FILENAME, read_job_events_after

logger = logging.getLogger(__name__)


async def _value(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def _encode(envelope: dict[str, Any]) -> str:
    event_name = "job" if envelope["trialName"] is None else "trial"
    data = json.dumps(envelope, ensure_ascii=False)
    return f"id: {envelope['id']}\nevent: {event_name}\ndata: {data}\n\n"


def _stream_error(job_name: str, message: str) -> str:
    data = json.dumps(
        {
            "jobName": job_name,
            "trialName": None,
            "event": {"type": "stream_error", "message": message},
        },
        ensure_ascii=False,
    )
    return f"event: stream_error\ndata: {data}\n\n"


async def stream_job_events(
    job_dir: Path,
    *,
    after: int,
    is_disconnected: Callable[[], Awaitable[bool]],
    is_terminal: Callable[[], bool | Awaitable[bool]],
    poll_seconds: float = 0.1,
    heartbeat_seconds: float = 15.0,
) -> AsyncIterator[str]:
    """Tail one job journal, replaying strictly after ``after``."""
    cursor = after
    idle_since = time.monotonic()
    path = job_dir / JOB_EVENTS_FILENAME
    try:
        while not await is_disconnected():
            envelopes, cursor = read_job_events_after(path, cursor)
            for envelope in envelopes:
                if await is_disconnected():
                    return
                yield _encode(envelope)
                idle_since = time.monotonic()

            if await _value(is_terminal()):
                envelopes, cursor = read_job_events_after(path, cursor)
                for envelope in envelopes:
                    if await is_disconnected():
                        return
                    yield _encode(envelope)
                return

            if time.monotonic() - idle_since >= heartbeat_seconds:
                yield ": heartbeat\n\n"
                idle_since = time.monotonic()
            await asyncio.sleep(max(0.0, poll_seconds))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        logger.exception("Harbor job event stream failed for %s", job_dir.name)
        if not await is_disconnected():
            yield _stream_error(job_dir.name, str(exc) or type(exc).__name__)
