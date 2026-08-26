"""Durable NDJSON event streams for Harbor trials and jobs.

Trial streams retain their historic ``events.jsonl`` format. Every trial
append also mirrors the event to a job-level journal whose newline-ending byte
offsets are stable resumable event identifiers.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO, Iterator

EVENTS_FILENAME = "events.jsonl"
JOB_EVENTS_FILENAME = "live-events.jsonl"


@contextmanager
def _exclusive_file_lock(handle: BinaryIO) -> Iterator[None]:
    """Hold a cross-process append lock on POSIX or Windows.

    POSIX writers share ``flock``; on Windows the standard-library ``msvcrt``
    byte-range lock protects byte zero. Unknown platforms fail closed instead
    of silently permitting interleaved journal records.
    """
    try:
        import fcntl
    except ImportError:
        fcntl = None  # type: ignore[assignment]

    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return

    try:
        import msvcrt
    except ImportError as exc:  # pragma: no cover - unsupported Python platform
        raise RuntimeError("job event locking is unsupported on this platform") from exc

    handle.seek(0)
    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
    try:
        yield
    finally:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


@contextmanager
def _no_lock() -> Iterator[None]:
    yield


def _write_line(path: Path, payload: dict[str, Any], *, lock: bool) -> int:
    encoded = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        with _exclusive_file_lock(handle) if lock else _no_lock():
            handle.seek(0, os.SEEK_END)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
            return handle.tell()


def append_job_event(
    job_dir: Path, *, trial_name: str | None, event: dict[str, Any]
) -> int:
    """Append a job envelope and return its stable ending-byte-offset ID."""
    if not isinstance(event, dict):
        raise TypeError("job event must be a mapping")
    if trial_name is not None and not isinstance(trial_name, str):
        raise TypeError("trial name must be a string or None")
    return _write_line(
        job_dir / JOB_EVENTS_FILENAME,
        {"trialName": trial_name, "event": event},
        lock=True,
    )


class TrialEventWriter:
    """Append a trial event and its job-journal mirror durably."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def for_trial_dir(cls, trial_dir: Path) -> "TrialEventWriter":
        return cls(trial_dir / EVENTS_FILENAME)

    def append(self, event: dict[str, Any]) -> None:
        if not isinstance(event, dict):
            raise TypeError("trial event must be a mapping")
        # The old feed is durable before its journal mirror becomes visible.
        # Writers pointed at a non-trial path must not recurse into a journal.
        _write_line(self._path, event, lock=False)
        if self._path.name != EVENTS_FILENAME:
            return
        trial_dir = self._path.parent
        append_job_event(trial_dir.parent, trial_name=trial_dir.name, event=event)


def _validate_cursor(raw: int, size: int, data: bytes, *, name: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f"{name} cursor must be a non-negative integer")
    if raw < 0 or raw > size:
        raise ValueError(f"{name} cursor is outside the journal")
    if raw and data[raw - 1 : raw] != b"\n":
        raise ValueError(f"{name} cursor must be a complete-line byte offset")
    return raw


def validate_event_cursor(path: Path, after: int) -> int:
    """Validate a byte cursor without parsing journal records.

    Routes use this before starting a response so malformed resume positions
    receive a client error, while later read/serialization failures can still
    be represented by a terminal ``stream_error`` SSE event.
    """
    if not path.is_file():
        if after:
            raise ValueError("event cursor is outside the journal")
        return 0
    data = path.read_bytes()
    return _validate_cursor(after, len(data), data, name="event")


def _read_json_lines_after(
    path: Path, after: int, *, decorate_job: bool
) -> tuple[list[dict[str, Any]], int]:
    if not path.is_file():
        if after:
            raise ValueError("event cursor is outside the journal")
        return [], 0
    data = path.read_bytes()
    cursor = _validate_cursor(after, len(data), data, name="event")
    events: list[dict[str, Any]] = []
    while cursor < len(data):
        newline = data.find(b"\n", cursor)
        if newline < 0:
            break
        end = newline + 1
        line = data[cursor:newline]
        cursor = end
        if not line.strip():
            continue
        try:
            value = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("malformed complete event record") from exc
        if not isinstance(value, dict):
            raise ValueError("malformed complete event record")
        if not decorate_job:
            events.append(value)
            continue
        trial_name = value.get("trialName")
        event = value.get("event")
        if (trial_name is not None and not isinstance(trial_name, str)) or not isinstance(
            event, dict
        ):
            raise ValueError("malformed complete event record")
        events.append(
            {
                "id": end,
                "jobName": path.parent.name,
                "trialName": trial_name,
                "event": event,
            }
        )
    return events, cursor


def read_events_after(path: Path, after: int = 0) -> tuple[list[dict[str, Any]], int]:
    """Return trial events using the historic character-offset semantics.

    The existing per-trial incremental endpoint exposes text offsets and has
    always clamped a stale/out-of-range cursor. Keep that compatibility
    contract separate from the strict binary cursors used by the job journal.
    """
    if not path.is_file():
        return [], 0
    text = path.read_text(encoding="utf-8")
    consumed = max(0, min(after, len(text)))
    if consumed >= len(text):
        return [], consumed

    events: list[dict[str, Any]] = []
    while consumed < len(text):
        newline = text.find("\n", consumed)
        if newline == -1:
            break
        line = text[consumed:newline]
        consumed = newline + 1
        stripped = line.strip()
        if stripped:
            events.append(json.loads(stripped))
    return events, consumed


def read_job_events_after(
    path: Path, after: int = 0
) -> tuple[list[dict[str, Any]], int]:
    """Read complete job records after a validated byte cursor.

    A record's ID is the byte offset immediately following its newline. An
    incomplete trailing write is deliberately left unread.
    """
    return _read_json_lines_after(path, after, decorate_job=True)
