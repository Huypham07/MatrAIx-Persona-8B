"""Tests for Harbor trial NDJSON event streams."""

from __future__ import annotations

import multiprocessing
from pathlib import Path

import pytest

from backend.api.sse_stream import stream_job_events
from playground.harbor.trial_events import (
    JOB_EVENTS_FILENAME,
    TrialEventWriter,
    append_job_event,
    read_events_after,
    read_job_events_after,
)


def _append_from_process(job_dir: str, trial_name: str, index: int) -> None:
    append_job_event(
        Path(job_dir),
        trial_name=trial_name,
        event={"type": "phase", "index": index},
    )


def test_trial_event_writer_and_incremental_read(tmp_path: Path) -> None:
    events_path = tmp_path / "trial-0" / "events.jsonl"
    writer = TrialEventWriter(events_path)

    writer.append({"type": "phase", "phase": "persona_kickoff"})
    writer.append({"type": "turn", "turn": {"turnIndex": 1, "userMessage": "hi", "assistantMessage": "hello"}})

    first, offset = read_events_after(events_path, 0)
    assert len(first) == 2
    assert first[0]["phase"] == "persona_kickoff"
    assert first[1]["turn"]["assistantMessage"] == "hello"

    writer.append({"type": "phase", "phase": "persona_thinking"})
    second, offset = read_events_after(events_path, offset)
    assert len(second) == 1
    assert second[0]["phase"] == "persona_thinking"

    all_events, _ = read_events_after(events_path, 0)
    assert len(all_events) == 3


def test_read_events_after_missing_file(tmp_path: Path) -> None:
    events, offset = read_events_after(tmp_path / "missing.jsonl", 0)
    assert events == []
    assert offset == 0


def test_job_journal_multiplexes_trials_and_replays_by_byte_cursor(tmp_path: Path) -> None:
    job_dir = tmp_path / "job-東京"
    TrialEventWriter.for_trial_dir(job_dir / "a").append(
        {"type": "phase", "phase": "running"}
    )
    TrialEventWriter.for_trial_dir(job_dir / "b").append(
        {"type": "survey_answer", "questionId": "q1", "value": "café"}
    )

    first, cursor = read_job_events_after(job_dir / JOB_EVENTS_FILENAME, 0)
    assert [item["trialName"] for item in first] == ["a", "b"]
    assert first[1]["jobName"] == "job-東京"
    assert first[1]["event"]["value"] == "café"
    assert first[-1]["id"] == cursor

    TrialEventWriter.for_trial_dir(job_dir / "a").append({"type": "done"})
    replay, next_cursor = read_job_events_after(job_dir / JOB_EVENTS_FILENAME, cursor)
    assert [item["event"]["type"] for item in replay] == ["done"]
    assert replay[0]["id"] == next_cursor > cursor


def test_job_journal_ignores_incomplete_tail_and_rejects_bad_cursor(tmp_path: Path) -> None:
    journal = tmp_path / "job" / JOB_EVENTS_FILENAME
    append_job_event(journal.parent, trial_name="trial-0", event={"type": "phase"})
    complete_size = journal.stat().st_size
    with journal.open("ab") as handle:
        handle.write(b'{"trialName":"trial-1"')

    events, cursor = read_job_events_after(journal, 0)
    assert [event["trialName"] for event in events] == ["trial-0"]
    assert cursor == complete_size
    with pytest.raises(ValueError, match="cursor"):
        read_job_events_after(journal, complete_size - 1)


def test_job_journal_rejects_malformed_complete_record(tmp_path: Path) -> None:
    journal = tmp_path / "job" / JOB_EVENTS_FILENAME
    journal.parent.mkdir()
    journal.write_bytes(b"not json\n")

    with pytest.raises(ValueError, match="malformed"):
        read_job_events_after(journal, 0)


def test_job_journal_serializes_concurrent_process_appends(tmp_path: Path) -> None:
    if "fork" not in multiprocessing.get_all_start_methods():
        pytest.skip("requires fork-capable platform")
    job_dir = tmp_path / "job"
    context = multiprocessing.get_context("fork")
    processes = [
        context.Process(target=_append_from_process, args=(str(job_dir), "trial", index))
        for index in range(12)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0

    events, cursor = read_job_events_after(job_dir / JOB_EVENTS_FILENAME, 0)
    assert sorted(event["event"]["index"] for event in events) == list(range(12))
    assert events[-1]["id"] == cursor


@pytest.mark.asyncio
async def test_sse_drains_terminal_job_and_stops_on_disconnect(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    append_job_event(job_dir, trial_name="a", event={"type": "done"})

    async def never_disconnected() -> bool:
        return False

    chunks = [
        chunk
        async for chunk in stream_job_events(
            job_dir,
            after=0,
            is_disconnected=never_disconnected,
            is_terminal=lambda: True,
            poll_seconds=0,
        )
    ]
    body = "".join(chunks)
    assert "event: trial\n" in body
    assert "id: " in body
    assert '"trialName": "a"' in body

    async def disconnected() -> bool:
        return True

    assert [
        chunk
        async for chunk in stream_job_events(
            job_dir,
            after=0,
            is_disconnected=disconnected,
            is_terminal=lambda: False,
            poll_seconds=0,
        )
    ] == []


@pytest.mark.asyncio
async def test_sse_heartbeats_while_idle_and_reports_read_errors(tmp_path: Path) -> None:
    job_dir = tmp_path / "idle-job"
    terminal_checks = 0

    def terminal_after_one_poll() -> bool:
        nonlocal terminal_checks
        terminal_checks += 1
        return terminal_checks > 1

    async def never_disconnected() -> bool:
        return False

    heartbeats = [
        chunk
        async for chunk in stream_job_events(
            job_dir,
            after=0,
            is_disconnected=never_disconnected,
            is_terminal=terminal_after_one_poll,
            poll_seconds=0,
            heartbeat_seconds=0,
        )
    ]
    assert heartbeats == [": heartbeat\n\n"]

    journal = job_dir / JOB_EVENTS_FILENAME
    journal.parent.mkdir(exist_ok=True)
    journal.write_bytes(b"bad json\n")
    errors = [
        chunk
        async for chunk in stream_job_events(
            job_dir,
            after=0,
            is_disconnected=never_disconnected,
            is_terminal=lambda: False,
            poll_seconds=0,
        )
    ]
    assert len(errors) == 1
    assert "event: stream_error\n" in errors[0]
