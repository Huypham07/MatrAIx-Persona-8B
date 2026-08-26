"""Build bounded ZIP exports for a Harbor job's evaluation traces."""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Iterable


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


ZipEntry = tuple[Path | bytes, str]


def _zip(files: Iterable[ZipEntry]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source, archive_name in files:
            if isinstance(source, bytes):
                archive.writestr(archive_name, source)
            else:
                archive.write(source, archive_name)
    return buffer.getvalue()


def _markdown_fence(value: str, language: str = "text") -> str:
    """Wrap text without escaping its real line breaks."""
    longest = max((len(match.group(0)) for match in re.finditer(r"`+", value)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{language}\n{value}\n{fence}"


def _readable_message_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
                else:
                    parts.append(json.dumps(item, ensure_ascii=False, indent=2))
            else:
                parts.append(str(item))
        return "\n\n".join(parts)
    if value is None:
        return ""
    if isinstance(value, (dict, tuple)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _readable_structured_value(value: Any, heading_level: int = 4) -> list[str]:
    """Render nested output values while preserving newlines inside strings."""
    heading = "#" * min(6, heading_level)
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            lines.extend(
                [
                    f"{heading} `{key}`",
                    "",
                    *_readable_structured_value(item, heading_level + 1),
                    "",
                ]
            )
        return lines or ["_Empty object_"]
    if isinstance(value, list):
        lines = []
        for index, item in enumerate(value, start=1):
            lines.extend(
                [
                    f"{heading} Item {index}",
                    "",
                    *_readable_structured_value(item, heading_level + 1),
                    "",
                ]
            )
        return lines or ["_Empty list_"]
    if isinstance(value, str):
        return [_markdown_fence(value)]
    if value is None:
        return ["`null`"]
    return [f"`{str(value).lower() if isinstance(value, bool) else value}`"]


def _readable_response(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [_markdown_fence(value)]
        if isinstance(parsed, (dict, list)):
            return _readable_structured_value(parsed)
        return [_markdown_fence(value)]
    return _readable_structured_value(value)


def _readable_llm_calls(path: Path) -> bytes | None:
    records = _read_jsonl(path)
    if not records:
        return None

    lines = [
        "# LLM prompts and responses",
        "",
        "Human-readable companion to `llm_calls.jsonl`. The JSONL file remains the canonical machine-readable trace.",
        "",
    ]
    for index, record in enumerate(records, start=1):
        step = str(record.get("step") or "LLM call")
        lines.extend([f"## Call {index}: {step}", ""])
        facts = [
            ("Call ID", record.get("callId")),
            ("Timestamp", record.get("timestamp")),
            ("Model", record.get("model")),
            ("Provider", record.get("provider")),
            ("Attempt", record.get("attempt")),
            ("Duration", f'{record["durationMs"]} ms' if record.get("durationMs") is not None else None),
            ("Finish reason", record.get("finishReason")),
        ]
        for label, value in facts:
            if value is not None and str(value).strip():
                lines.append(f"- **{label}:** {value}")
        lines.append("")

        messages = record.get("messages")
        if isinstance(messages, list):
            for message_index, message in enumerate(messages, start=1):
                if not isinstance(message, dict):
                    continue
                role = str(message.get("role") or "message").title()
                content = _readable_message_content(message.get("content"))
                lines.extend(
                    [
                        f"### Prompt message {message_index}: {role}",
                        "",
                        _markdown_fence(content),
                        "",
                    ]
                )

        raw_output = record.get("rawOutput")
        if raw_output is not None:
            lines.extend(
                [
                    "### Raw response",
                    "",
                    *_readable_response(raw_output),
                    "",
                ]
            )

        if record.get("parsedOutput") is not None:
            lines.extend(
                [
                    "### Parsed response",
                    "",
                    *_readable_structured_value(record["parsedOutput"]),
                    "",
                ]
            )

        if record.get("usage") is not None:
            usage = json.dumps(record["usage"], ensure_ascii=False, indent=2)
            lines.extend(["### Usage", "", _markdown_fence(usage, "json"), ""])

        if record.get("error"):
            lines.extend(
                ["### Error", "", _markdown_fence(_readable_message_content(record["error"])), ""]
            )

    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def _readable_trial_entries(trial_dir: Path, archive_root: str) -> list[ZipEntry]:
    """Generate optional human-readable companions without changing source artifacts."""
    llm_calls = trial_dir / "llm_calls.jsonl"
    if not llm_calls.is_file() or llm_calls.is_symlink():
        return []
    rendered = _readable_llm_calls(llm_calls)
    if rendered is None:
        return []
    return [(rendered, f"{archive_root}/readable/llm_calls.md")]


def _filename_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.") or "trace"


def build_trial_trace_zip(jobs_dir: Path, job_name: str, trial_name: str) -> tuple[bytes, str]:
    job_dir = _resolve_child(Path(jobs_dir), job_name, "job")
    trial_dir = _resolve_child(job_dir, trial_name, "trial")
    files = [
        (path, f"{trial_name}/{path.relative_to(trial_dir).as_posix()}")
        for path in _trial_files(trial_dir)
    ]
    files.extend(_readable_trial_entries(trial_dir, trial_name))
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
        files.extend(
            _readable_trial_entries(trial_dir, f"{job_name}/{trial_dir.name}")
        )
    return _zip(files), f"{_filename_part(job_name)}-traces.zip"
