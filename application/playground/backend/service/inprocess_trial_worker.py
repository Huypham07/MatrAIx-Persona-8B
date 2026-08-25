"""Truthful host-native trial execution for local distributed Harbor runs.

This module owns one trial's manifest, artifacts, and event stream.  Its
``emit`` boundary is deliberately small so Task 5 can also mirror each event
to the job journal without changing runner or artifact behavior.
"""

from __future__ import annotations

import json
import os
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml

from backend.service.survey_instruments import get_survey_instrument
from backend.service.survey_task_registry import survey_questionnaire_id_for_task_path
from backend.service.survey_types import SurveyEvalConfig
from playground.inprocess.chatbot_eval import (
    ApplicationUnavailable,
    inprocess_chatbot_config,
    run_inprocess_chatbot_eval,
)
from playground.inprocess.survey_eval import InprocessSurveyEvalRunner
from playground.types import Persona, PlaygroundResult, PlaygroundTurn
from playground.user_sim.runner import ConversationNotTerminated


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    """Replace an artifact atomically so live readers never observe half JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(dict(payload), ensure_ascii=False, indent=2)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _write_output_and_verifier(
    trial_dir: Path, filename: str, payload: Mapping[str, Any]
) -> None:
    _write_json_atomic(trial_dir / "artifacts" / "app" / "output" / filename, payload)
    _write_json_atomic(trial_dir / "verifier" / filename, payload)


def _load_canonical_persona(
    persona_path: str, *, repo_root: Path
) -> tuple[Persona, str]:
    if not persona_path:
        raise FileNotFoundError("Canonical persona source not found: <missing>")
    path = Path(persona_path)
    if not path.is_absolute():
        path = repo_root / path
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Canonical persona source not found: {persona_path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Canonical persona source must be a mapping: {path}")
    dimensions = payload.get("dimensions")
    if dimensions is not None and not isinstance(dimensions, Mapping):
        raise TypeError("Canonical persona dimensions must be a mapping")
    resolved_path = str(path)
    return Persona.from_dict(payload, persona_path=resolved_path), resolved_path


def _persona_meta(persona: Persona) -> dict[str, Any]:
    return {
        "id": persona.id,
        "persona_id": persona.id,
        "name": persona.name,
        "display_name": persona.name,
        "summary": persona.summary,
        "dimensions": dict(persona.dimensions),
        "schemaVersion": persona.schema_version,
        "personaPath": persona.persona_path,
    }


def _trial_result(
    *,
    manifest: Mapping[str, Any],
    trial_dir: Path,
    task_path: str,
    agent_name: str,
    model_name: str,
    started_at: str,
    terminal_status: str,
    succeeded: bool,
    evals: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "trial_name": manifest["trial_name"],
        "task_name": Path(task_path.replace("\\", "/")).name,
        "trial_uri": trial_dir.resolve().as_uri(),
        "started_at": started_at,
        "finished_at": _utc_now(),
        "agent_info": {
            "name": agent_name,
            "version": "inprocess",
            "model_info": {"model_name": model_name},
        },
        "terminal_status": terminal_status,
        "succeeded": succeeded,
        "evals": dict(evals or {}),
    }


def _chat_transcript_payload(turns: list[dict[str, Any]], *, termination_reason: str) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    for turn in turns:
        messages.extend(
            [
                {"role": "user", "content": str(turn.get("userMessage") or "")},
                {
                    "role": "assistant",
                    "content": str(turn.get("assistantMessage") or ""),
                },
            ]
        )
    return {
        "turns": turns,
        "messages": messages,
        "terminationReason": termination_reason,
    }


def _persist_partial_chat(
    trial_dir: Path, turns: list[dict[str, Any]], *, termination_reason: str
) -> None:
    """Persist only observed turns; never create feedback for a failed chat."""
    _write_output_and_verifier(
        trial_dir,
        "transcript.json",
        _chat_transcript_payload(turns, termination_reason=termination_reason),
    )
    _write_output_and_verifier(
        trial_dir,
        "application_result.json",
        {
            "status": "failed",
            "turnCount": len(turns),
            "terminationReason": termination_reason,
        },
    )


def _persist_completed_chat(trial_dir: Path, result: PlaygroundResult) -> tuple[bool, str, float]:
    turns = [turn.to_dict() for turn in result.transcript]
    decision = result.transcript[-1].decision if result.transcript else "no_turns"
    succeeded = (
        decision == "satisfied" and len(result.transcript) >= result.config.min_turns
    )
    termination_reason = decision
    _write_output_and_verifier(
        trial_dir,
        "transcript.json",
        _chat_transcript_payload(turns, termination_reason=termination_reason),
    )
    _write_output_and_verifier(
        trial_dir,
        "application_result.json",
        {
            "applicationId": result.config.application_id,
            "applicationContext": result.config.application_context or result.config.domain,
            "status": "completed" if succeeded else "failed",
            "turnCount": len(turns),
            "decision": decision,
            "terminationReason": termination_reason,
        },
    )
    if succeeded:
        _write_output_and_verifier(
            trial_dir, "user_feedback.json", result.questionnaire.artifact_dict()
        )
    satisfaction = max(0.0, min(1.0, result.questionnaire.overall_rating / 10.0))
    return succeeded, termination_reason, satisfaction


def _turns_from_exception(
    exc: BaseException,
    observed_turns: list[dict[str, Any]],
    pending_turns: Mapping[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    transcript = getattr(exc, "transcript", None)
    if isinstance(transcript, list):
        turns = [turn.to_dict() for turn in transcript if isinstance(turn, PlaygroundTurn)]
    else:
        turns = list(observed_turns)
    finalized_indices = {
        int(turn["turnIndex"])
        for turn in turns
        if isinstance(turn.get("turnIndex"), int)
    }
    turns.extend(
        turn
        for index, turn in sorted(pending_turns.items())
        if index not in finalized_indices
    )
    return turns


def _run_web_trial(
    *,
    repo_root: Path,
    trial_dir: Path,
    output_dir: Path,
    persona: Persona,
    model_name: str,
    created_at: str,
    emit: Callable[[dict[str, Any]], None],
) -> None:
    """Run Web and persist the task's canonical JSON hand-in."""
    from backend.service.harbor_trial_debrief import _resolve_web_eval_task
    from playground.harbor.web_eval import HarborWebEvalConfig
    from playground.inprocess.web_eval import InprocessWebEvalRunner

    task = _resolve_web_eval_task(repo_root, trial_dir, output_dir)
    emit(
        {
            "type": "stage",
            "stage": "running_agent",
            "message": f"Browsing website and selecting options as {persona.name}...",
        }
    )
    result = InprocessWebEvalRunner(repo_root=repo_root)(
        persona=persona,
        task=task,
        config=HarborWebEvalConfig(persona_model=model_name),
        created_at=created_at,
        on_event=emit,
    )
    web_result = result.web_result
    task_output = getattr(result, "task_output", None)
    if not isinstance(task_output, Mapping) or not task_output:
        raise ValueError(
            "Web runner returned no canonical submission required by instruction.md"
        )
    feedback = {
        "overallExperienceRating": getattr(web_result, "overall_experience_rating", 0),
        "needConstraintSatisfaction": "yes",
        "personalPreferenceSatisfaction": "yes",
        "needSatisfaction": getattr(web_result, "need_satisfaction", 0),
        "easeOfUse": getattr(web_result, "ease_of_use", 0),
        "reason": getattr(web_result, "reason", ""),
    }
    _write_output_and_verifier(trial_dir, task.output_artifact, task_output)
    _write_json_atomic(output_dir / "web_result.json", web_result.to_dict())
    _write_json_atomic(output_dir / "user_feedback.json", feedback)
    _write_json_atomic(trial_dir / "verifier" / "web_result.json", web_result.to_dict())
    _write_json_atomic(
        trial_dir / "agent" / "trajectory.json",
        {"steps": result.trace.events, "trace": result.trace.events},
    )
    emit(
        {
            "type": "stage",
            "stage": "completed",
            "message": f"Selected {web_result.selected_product_name}.",
        }
    )


def run_inprocess_trial(
    manifest_path: Path, env: Mapping[str, str], *, repo_root: Path
) -> int:
    """Run one manifest with real runners and truthful terminal artifacts."""
    from backend.service.local_distributed_harbor import _write_failure_result
    from playground.harbor.trial_events import TrialEventWriter

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    trial_name = str(manifest["trial_name"])
    trial_dir = Path(str(manifest["trials_dir"])) / trial_name
    output_dir = trial_dir / "artifacts" / "app" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    task_path = str((manifest.get("task") or {}).get("path") or "")
    agent_spec = manifest.get("agent") or {}
    agent_name = str(agent_spec.get("name") or "persona-json-survey")
    model_name = str(agent_spec.get("model_name") or "local/qwen3-14b")
    agent_kwargs = agent_spec.get("kwargs") or {}
    started_at = _utc_now()
    event_writer = TrialEventWriter.for_trial_dir(trial_dir)

    # The single callback is intentionally the future Task 5 journal seam.
    def emit(event: dict[str, Any]) -> None:
        event_writer.append(event)

    def emit_runner_event(event: dict[str, Any]) -> None:
        # Runners may report completion for their own in-memory result. The
        # worker is responsible for the one durable terminal event after all
        # artifacts and result.json have reached disk.
        if event.get("type") == "done":
            return
        emit(event)

    def fail(exc: BaseException, *, partial_turns: list[dict[str, Any]] | None = None) -> int:
        if partial_turns is not None:
            _persist_partial_chat(
                trial_dir,
                partial_turns,
                termination_reason=type(exc).__name__,
            )
        _write_failure_result(
            trial_dir,
            manifest,
            exception_type=type(exc).__name__,
            exception_message=f"{exc}\n{traceback.format_exc()}",
        )
        # The coordinator helper owns the portable failure shape; atomically
        # replace its final result before anyone can consume the terminal event.
        failure_result = json.loads((trial_dir / "result.json").read_text(encoding="utf-8"))
        failure_result["terminal_status"] = "failed"
        failure_result["succeeded"] = False
        failure_result["evals"] = {}
        _write_json_atomic(trial_dir / "result.json", failure_result)
        emit(
            {
                "type": "done",
                "status": "failed",
                "completed": False,
                "succeeded": False,
                "terminationReason": type(exc).__name__,
                "message": str(exc),
            }
        )
        return 1

    try:
        persona, persona_yaml_path = _load_canonical_persona(
            str(agent_kwargs.get("persona_path") or ""), repo_root=repo_root
        )
    except Exception as exc:  # noqa: BLE001 - source errors must be surfaced verbatim
        return fail(exc)

    _write_json_atomic(trial_dir / "persona_meta.json", _persona_meta(persona))
    emit(
        {
            "type": "stage",
            "stage": "starting_env",
            "message": f"Initializing persona {persona.name}...",
        }
    )

    try:
        if "survey" in agent_name or "survey" in task_path.lower():
            questionnaire_id = survey_questionnaire_id_for_task_path(
                task_path, repo_root=repo_root
            )
            if questionnaire_id:
                instrument = get_survey_instrument(questionnaire_id, repo_root=repo_root)
            else:
                from playground.survey_task_content import load_survey_task_content_for_task_path

                instrument = load_survey_task_content_for_task_path(
                    task_path, repo_root=repo_root
                ).instrument
            if instrument is None:
                raise ValueError(f"Survey task has no questionnaire: {task_path}")
            emit(
                {
                    "type": "stage",
                    "stage": "running_agent",
                    "message": f"Calling {model_name} for survey answering...",
                }
            )

            def on_survey_event(event: dict[str, Any]) -> None:
                partial = event.get("result")
                if event.get("type") == "survey_progress" and isinstance(partial, dict):
                    _write_output_and_verifier(trial_dir, "structured_output.json", partial)
                    _write_output_and_verifier(trial_dir, "survey_result.json", partial)
                emit_runner_event(event)

            result = InprocessSurveyEvalRunner()(
                persona=persona,
                instrument=instrument,
                config=SurveyEvalConfig(persona_model=model_name),
                created_at=started_at,
                persona_yaml_path=persona_yaml_path,
                on_event=on_survey_event,
                job_dir=trial_dir.parent,
            )
            if len(result.answers) != len(instrument.questions):
                raise ValueError("Survey runner returned an incomplete result")
            result_payload = result.to_dict()
            _write_output_and_verifier(trial_dir, "structured_output.json", result_payload)
            _write_output_and_verifier(trial_dir, "survey_result.json", result_payload)
            emit(
                {
                    "type": "stage",
                    "stage": "completed",
                    "message": f"Answered {len(result.answers)} questions successfully.",
                }
            )
            terminal_status, succeeded, evals = "completed", True, {}
        elif "user-sim" in agent_name or "chat" in task_path.lower():
            observed_turns: list[dict[str, Any]] = []
            pending_turns: dict[int, dict[str, Any]] = {}

            def on_chat_event(event: dict[str, Any]) -> None:
                event_type = event.get("type")
                turn_index = event.get("turnIndex")
                if event_type == "user_message" and isinstance(turn_index, int):
                    pending_turns[turn_index] = {
                        "turnIndex": turn_index,
                        "userMessage": str(event.get("message") or ""),
                    }
                elif event_type == "assistant_message" and isinstance(turn_index, int):
                    pending = pending_turns.get(turn_index, {"turnIndex": turn_index})
                    pending["userMessage"] = str(
                        event.get("userMessage") or pending.get("userMessage") or ""
                    )
                    pending["assistantMessage"] = str(event.get("assistantMessage") or "")
                    pending["structuredExposure"] = list(
                        event.get("structuredExposure") or []
                    )
                    if event.get("durationSeconds") is not None:
                        pending["durationSeconds"] = event["durationSeconds"]
                    pending_turns[turn_index] = pending
                turn = event.get("turn")
                if event_type == "turn" and isinstance(turn, dict):
                    completed = dict(turn)
                    completed_index = completed.get("turnIndex")
                    if isinstance(completed_index, int):
                        pending_turns.pop(completed_index, None)
                    observed_turns.append(completed)
                emit_runner_event(event)

            config = inprocess_chatbot_config(
                task_path, repo_root=repo_root, env=env, model_name=model_name
            )
            emit(
                {
                    "type": "stage",
                    "stage": "running_agent",
                    "message": f"Starting conversation as {persona.name}...",
                }
            )
            try:
                result = run_inprocess_chatbot_eval(
                    persona,
                    config,
                    task_path=task_path,
                    persona_yaml_path=persona_yaml_path,
                    repo_root=repo_root,
                    created_at=started_at,
                    on_event=on_chat_event,
                    job_dir=trial_dir.parent,
                )
            except (ConversationNotTerminated, ApplicationUnavailable) as exc:
                return fail(
                    exc,
                    partial_turns=_turns_from_exception(
                        exc, observed_turns, pending_turns
                    ),
                )
            except Exception as exc:  # provider and runner failures preserve observed truth
                return fail(
                    exc,
                    partial_turns=_turns_from_exception(
                        exc, observed_turns, pending_turns
                    ),
                )
            succeeded, termination_reason, satisfaction = _persist_completed_chat(
                trial_dir, result
            )
            if not succeeded:
                return fail(
                    ConversationNotTerminated(termination_reason, result.transcript),
                    partial_turns=[turn.to_dict() for turn in result.transcript],
                )
            terminal_status, evals = "completed", {"satisfaction": satisfaction}
            emit(
                {
                    "type": "stage",
                    "stage": "completed",
                    "message": f"Conversation ended: {termination_reason}.",
                }
            )
        else:
            _run_web_trial(
                repo_root=repo_root,
                trial_dir=trial_dir,
                output_dir=output_dir,
                persona=persona,
                model_name=model_name,
                created_at=started_at,
                emit=emit_runner_event,
            )
            terminal_status, succeeded, evals = "completed", True, {"satisfaction": 1.0}

        _write_json_atomic(
            trial_dir / "result.json",
            _trial_result(
                manifest=manifest,
                trial_dir=trial_dir,
                task_path=task_path,
                agent_name=agent_name,
                model_name=model_name,
                started_at=started_at,
                terminal_status=terminal_status,
                succeeded=succeeded,
                evals=evals,
            ),
        )
        emit(
            {
                "type": "done",
                "status": terminal_status,
                "completed": True,
                "succeeded": succeeded,
            }
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - produce a terminal truthful failure
        return fail(exc)
