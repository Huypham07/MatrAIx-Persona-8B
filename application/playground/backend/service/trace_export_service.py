"""Build bounded ZIP exports for a Harbor job's evaluation traces."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Iterable


_TRIAL_ROOT_FILES = {
    "config.json",
    "result.json",
    "events.jsonl",
    "llm_calls.jsonl",
    "persona_meta.json",
    "instruction.md",
    "task_instruction.md",
    "context.md",
    "questionnaire.md",
    "output_schema.md",
    "exception.txt",
    "reward.txt",
    "trial.log",
}
_TRIAL_DIRS = (
    "agent",
    "logs",
    "verifier",
    "artifacts/app/output",
)
_JOB_ROOT_FILES = {
    "config.json",
    "result.json",
    "events.jsonl",
    "job_events.jsonl",
    "lock.json",
}


def _validate_name(value: str, label: str) -> None:
    if not value or value in {".", ".."} or "/" in value or "\\" in value or ".." in value:
        raise ValueError(f"Invalid {label} name")


def _resolve_child(root: Path, name: str, label: str) -> Path:
    _validate_name(name, label)
    resolved_root = root.resolve()
    child = (resolved_root / name).resolve()
    try:
        child.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Invalid {label} name") from exc
    if not child.is_dir():
        raise ValueError(f"{label.title()} not found: {name}")
    return child


def _regular_files(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return ()
    return (
        path
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    )


def _trial_files(trial_dir: Path) -> list[Path]:
    files = [
        trial_dir / name
        for name in sorted(_TRIAL_ROOT_FILES)
        if (trial_dir / name).is_file() and not (trial_dir / name).is_symlink()
    ]
    for relative in _TRIAL_DIRS:
        files.extend(_regular_files(trial_dir / relative))
    return files


def _zip(files: Iterable[tuple[Path, str]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source, archive_name in files:
            archive.write(source, archive_name)
    return buffer.getvalue()


def _filename_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.") or "trace"


def build_trial_trace_zip(jobs_dir: Path, job_name: str, trial_name: str) -> tuple[bytes, str]:
    job_dir = _resolve_child(Path(jobs_dir), job_name, "job")
    trial_dir = _resolve_child(job_dir, trial_name, "trial")
    files = [
        (path, f"{trial_name}/{path.relative_to(trial_dir).as_posix()}")
        for path in _trial_files(trial_dir)
    ]
    filename = f"{_filename_part(job_name)}-{_filename_part(trial_name)}-trace.zip"
    return _zip(files), filename


def build_job_trace_zip(jobs_dir: Path, job_name: str) -> tuple[bytes, str]:
    job_dir = _resolve_child(Path(jobs_dir), job_name, "job")
    files: list[tuple[Path, str]] = [
        (job_dir / name, f"{job_name}/{name}")
        for name in sorted(_JOB_ROOT_FILES)
        if (job_dir / name).is_file() and not (job_dir / name).is_symlink()
    ]
    for trial_dir in sorted(job_dir.iterdir()):
        if not trial_dir.is_dir() or trial_dir.is_symlink() or trial_dir.name.startswith("_"):
            continue
        files.extend(
            (
                path,
                f"{job_name}/{trial_dir.name}/{path.relative_to(trial_dir).as_posix()}",
            )
            for path in _trial_files(trial_dir)
        )
    return _zip(files), f"{_filename_part(job_name)}-traces.zip"
