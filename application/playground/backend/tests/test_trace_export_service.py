from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from backend.service.trace_export_service import (
    build_job_trace_zip,
    build_trial_trace_zip,
)


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _names(payload: bytes) -> set[str]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return set(archive.namelist())


def test_trial_trace_zip_contains_prompts_trajectory_and_outputs(tmp_path: Path) -> None:
    trial = tmp_path / "job-1" / "trial-1"
    _write(trial / "llm_calls.jsonl", json.dumps({"messages": [], "rawOutput": "ok"}))
    _write(trial / "events.jsonl")
    _write(trial / "agent" / "trajectory.json")
    _write(trial / "artifacts" / "app" / "output" / "answers.json")
    _write(trial / "sandbox" / "secret.txt")

    payload, filename = build_trial_trace_zip(tmp_path, "job-1", "trial-1")

    assert filename == "job-1-trial-1-trace.zip"
    assert _names(payload) == {
        "trial-1/llm_calls.jsonl",
        "trial-1/events.jsonl",
        "trial-1/agent/trajectory.json",
        "trial-1/artifacts/app/output/answers.json",
    }


def test_job_trace_zip_contains_each_persona_trial(tmp_path: Path) -> None:
    job = tmp_path / "job-1"
    _write(job / "config.json")
    _write(job / "trial-a" / "persona_meta.json")
    _write(job / "trial-a" / "llm_calls.jsonl")
    _write(job / "trial-b" / "events.jsonl")

    payload, filename = build_job_trace_zip(tmp_path, "job-1")

    assert filename == "job-1-traces.zip"
    assert _names(payload) == {
        "job-1/config.json",
        "job-1/trial-a/persona_meta.json",
        "job-1/trial-a/llm_calls.jsonl",
        "job-1/trial-b/events.jsonl",
    }


@pytest.mark.parametrize("name", ["../job-1", "a/b", "", "."])
def test_trace_export_rejects_unsafe_names(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError):
        build_job_trace_zip(tmp_path, name)
