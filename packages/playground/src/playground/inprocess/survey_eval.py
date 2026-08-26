from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any, Callable, Dict, List, Optional

from backend.service.survey_instruction_builder import (
    render_survey_context_markdown,
    render_survey_output_schema_markdown,
    render_survey_questionnaire_markdown,
    render_survey_task_instruction_markdown,
)
from backend.service.survey_types import (
    SurveyAnswer,
    SurveyEvalConfig,
    SurveyEvalResult,
    SurveyInstrument,
    SurveyMetrics,
    SurveyQuestion,
    SurveyTaskContent,
    TrajectoryEvent,
)
from playground.budget import assert_budget_allows_request, record_trial_cost
from playground.llm_usage import LlmUsage, merge_usage
from playground.model_client import build_json_client
from playground.types import Persona
from playground.user_sim.prompt import (
    persona_language_contract,
    persona_primary_language,
    render_persona_block,
)


def persona_system_prompt(
    persona: Persona,
    *,
    persona_yaml_path: Optional[str] = None,
    task_path: Optional[str] = None,
    task_dir: Optional[Path | str] = None,
    include_fields: Optional[list[str] | set[str]] = None,
    exclude_fields: Optional[list[str] | set[str]] = None,
) -> str:
    persona_body = render_persona_block(
        persona,
        persona_yaml_path=persona_yaml_path,
        task_path=task_path,
        task_dir=task_dir,
        include_fields=include_fields,
        exclude_fields=exclude_fields,
    ).strip()
    if not persona_body:
        persona_body = persona.context or f"I am {persona.name} (Persona ID: {persona.id})."
    return "{}\n\n{}".format(persona_body, persona_language_contract(persona))


def build_survey_task_prompt(*, instrument: SurveyInstrument) -> str:
    return SurveyTaskContent(
        title=instrument.title,
        instruction_markdown=render_survey_task_instruction_markdown(instrument),
        context_markdown=render_survey_context_markdown(instrument),
        questionnaire_markdown=render_survey_questionnaire_markdown(instrument),
        output_schema_markdown=render_survey_output_schema_markdown(instrument),
        instrument=instrument,
    ).combined_markdown()


class InvalidSurveyResponse(ValueError):
    def __init__(self, question_id: str, detail: str) -> None:
        super().__init__(
            f"Invalid model response for survey question {question_id}: {detail}"
        )
        self.question_id = question_id
        self.detail = detail


def _validate_answer(
    raw: Any, question: SurveyQuestion, instrument: SurveyInstrument
) -> SurveyAnswer:
    payload = raw.get("answer") if isinstance(raw, dict) else None
    if not isinstance(payload, dict):
        raise InvalidSurveyResponse(question.id, "answer must be an object")
    try:
        answer = SurveyAnswer.from_dict(payload)
    except (TypeError, ValueError) as exc:
        raise InvalidSurveyResponse(question.id, str(exc)) from exc
    if answer.question_id != question.id:
        raise InvalidSurveyResponse(question.id, "questionId does not match")
    if question.type == "likert":
        if isinstance(answer.value, bool) or not str(answer.value).strip().isdigit():
            raise InvalidSurveyResponse(question.id, "value must be an integer")
        answer.value = int(answer.value)
        if not question.min_value <= answer.value <= question.max_value:
            raise InvalidSurveyResponse(
                question.id, "value is outside the authored range"
            )
    elif question.type == "single_choice" and str(answer.value) not in question.options:
        raise InvalidSurveyResponse(
            question.id, "value is not one of the authored option ids"
        )
    elif question.type == "multi_choice":
        if (
            not isinstance(answer.value, list)
            or not answer.value
            or any(str(value) not in question.options for value in answer.value)
        ):
            raise InvalidSurveyResponse(
                question.id, "values must be authored option ids"
            )
        answer.value = [str(value) for value in answer.value]
    elif question.type == "free_text" and not str(answer.value or "").strip():
        raise InvalidSurveyResponse(question.id, "free-text value must not be empty")
    answer.rationale = (
        answer.rationale if question.resolves_ask_rationale(instrument) else ""
    )
    answer.confidence = (
        answer.confidence if question.resolves_ask_confidence(instrument) else None
    )
    return answer


def _question_completion_prompt(
    *,
    instrument: SurveyInstrument,
    question: SurveyQuestion,
    answers: list[SurveyAnswer],
    correction_detail: str | None = None,
) -> str:
    question_instrument = SurveyInstrument(
        id=instrument.id,
        title=instrument.title,
        description=instrument.description,
        questions=[question],
        ask_rationale=instrument.ask_rationale,
        ask_confidence=instrument.ask_confidence,
    )
    parts = [
        f"# {instrument.title}",
        "",
        "## Task instruction",
        "",
        render_survey_task_instruction_markdown(instrument).strip(),
        "",
        "## Context",
        "",
        render_survey_context_markdown(instrument).strip(),
        "",
        "## Current question",
        "",
        render_survey_questionnaire_markdown(question_instrument).strip(),
        "",
        "## Required JSON format",
        "",
        "```json",
        '{"answer": {"questionId": "%s", "value": "<answer value>"}}'
        % question.id,
        "```",
        "",
        "Respond with valid JSON only.",
    ]
    if answers:
        continuity = [
            {"questionId": answer.question_id, "value": answer.value}
            for answer in answers
        ]
        parts.extend(
            [
                "",
                "## Previously answered questions",
                "",
                json.dumps(continuity, ensure_ascii=False),
            ]
        )
    if correction_detail is not None:
        parts.extend(
            [
                "",
                "## Correction required",
                "",
                "Your previous response was invalid: {}. Return a corrected answer for "
                "the current question using the required JSON format.".format(
                    correction_detail
                ),
            ]
        )
    return "\n".join(parts).strip()


class InprocessSurveyEvalRunner:
    """Run survey completion through the configured persona model."""

    def __call__(
        self,
        persona: Persona,
        instrument: SurveyInstrument,
        config: Optional[SurveyEvalConfig] = None,
        *,
        created_at: Optional[str] = None,
        persona_yaml_path: Optional[str] = None,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
        job_dir: Optional[Any] = None,
        trace_dir: Optional[Any] = None,
        segment_id: Optional[str] = None,
        task_path: Optional[str] = None,
        task_dir: Optional[Path | str] = None,
        client: Any | None = None,
        client_factory: Optional[Callable[[str], Any]] = None,
    ) -> SurveyEvalResult:
        config = config or SurveyEvalConfig()
        created_at = created_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        def emit(event: Dict[str, Any]) -> None:
            if on_event is not None:
                on_event(event)

        task_prompt = build_survey_task_prompt(instrument=instrument)
        persona_prompt = persona_system_prompt(
            persona,
            persona_yaml_path=persona_yaml_path,
            task_path=task_path,
            task_dir=task_dir,
        )
        prompts = {
            "personaPrompt": persona_prompt,
            "harborPrompt": persona_prompt,
            "taskPrompt": task_prompt,
        }
        expected_language = persona_primary_language(persona)
        trace_writer = None
        if trace_dir is not None:
            from pathlib import Path

            from playground.llm_trace import LlmTraceWriter

            trace_root = Path(trace_dir)
            trace_writer = LlmTraceWriter(
                trace_root / "llm_calls.jsonl",
                metadata={
                    "jobId": trace_root.parent.name,
                    "trialId": trace_root.name,
                    "taskId": instrument.id,
                    "personaId": persona.id,
                    "segmentId": segment_id,
                    "expectedLanguage": expected_language,
                },
            )
        if client is None:
            if client_factory is not None:
                client = client_factory(config.persona_model)
            elif trace_writer is None:
                client = build_json_client(config.persona_model)
            else:
                client = build_json_client(
                    config.persona_model,
                    trace_writer=trace_writer,
                    trace_step="survey_answer",
                )

        all_answers: list[SurveyAnswer] = []
        usage_parts: list[LlmUsage | None] = []

        for index, question in enumerate(instrument.questions, start=1):
            emit(
                {
                    "type": "survey_question_started",
                    "questionId": question.id,
                    "prompt": question.prompt,
                    "questionType": question.type,
                    "questionIndex": index,
                    "numQuestions": len(instrument.questions),
                    "expectedLanguage": expected_language,
                }
            )
            emit(
                {
                    "type": "stage",
                    "stage": "running_agent",
                    "message": "Answering Q{}/{}: {}...".format(
                        index, len(instrument.questions), question.prompt[:60]
                    ),
                }
            )
            emit({"type": "phase", "phase": "survey_answering"})

            correction_detail: str | None = None
            for attempt in range(2):
                question_prompt = _question_completion_prompt(
                    instrument=instrument,
                    question=question,
                    answers=all_answers,
                    correction_detail=correction_detail,
                )
                assert_budget_allows_request(job_dir)
                try:
                    if hasattr(client, "complete_json_with_usage"):
                        completion = client.complete_json_with_usage(
                            prompts["personaPrompt"], question_prompt
                        )
                        raw = completion.data
                        usage = completion.usage
                    else:
                        raw = client.complete_json(
                            prompts["personaPrompt"], question_prompt
                        )
                        usage = None
                except ValueError as exc:
                    invalid_response = InvalidSurveyResponse(question.id, str(exc))
                    if attempt == 1:
                        raise invalid_response from exc
                    correction_detail = invalid_response.detail
                    continue
                usage_parts.append(usage)
                if usage is not None:
                    record_trial_cost(job_dir, usage.cost_usd)

                try:
                    answer = _validate_answer(raw, question, instrument)
                except InvalidSurveyResponse as exc:
                    if attempt == 1:
                        raise
                    correction_detail = exc.detail
                    continue
                break
            else:  # pragma: no cover - the second attempt either breaks or raises.
                raise AssertionError("survey answer loop exhausted without a response")

            all_answers.append(answer)
            total_usage = merge_usage(*usage_parts)
            emit(
                {
                    "type": "survey_answer",
                    "questionId": answer.question_id,
                    "value": answer.value,
                    "rationale": answer.rationale,
                    "confidence": answer.confidence,
                    "progress": f"{len(all_answers)}/{len(instrument.questions)}",
                    "message": f"Answered [{answer.question_id}]: {answer.value}",
                    "expectedLanguage": expected_language,
                }
            )
            intermediate_result = SurveyEvalResult(
                config=config,
                persona=persona,
                instrument=instrument,
                answers=list(all_answers),
                trajectory=_build_trajectory(
                    instrument, all_answers, created_at, completed=False
                ),
                metrics=_metrics(all_answers, instrument),
                created_at=created_at,
                prompts=prompts,
                usage=total_usage.to_dict() if total_usage is not None else None,
            )
            emit(
                {
                    "type": "survey_progress",
                    "progress": f"{len(all_answers)}/{len(instrument.questions)}",
                    "result": intermediate_result.to_dict(),
                }
            )

        answers = all_answers
        total_usage = merge_usage(*usage_parts)
        metrics = _metrics(answers, instrument)
        trajectory = _build_trajectory(instrument, answers, created_at)
        result = SurveyEvalResult(
            config=config,
            persona=persona,
            instrument=instrument,
            answers=answers,
            trajectory=trajectory,
            metrics=metrics,
            created_at=created_at,
            prompts=prompts,
            usage=total_usage.to_dict() if total_usage is not None else None,
        )
        emit({
            "type": "stage",
            "stage": "completed",
            "message": f"All {len(answers)} questions answered successfully.",
        })
        emit({"type": "done", "result": result.to_dict()})
        return result


def _event_timestamp(created_at: str, offset_seconds: int) -> str:
    try:
        base = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return created_at
    return (
        base.astimezone(timezone.utc) + timedelta(seconds=offset_seconds)
    ).isoformat().replace("+00:00", "Z")


def _build_trajectory(
    instrument: SurveyInstrument,
    answers: List[SurveyAnswer],
    created_at: str,
    *,
    completed: bool = True,
) -> List[TrajectoryEvent]:
    answer_by_id = {answer.question_id: answer for answer in answers}
    missing_required = [
        question.id
        for question in instrument.questions
        if question.required and question.id not in answer_by_id
    ]
    events = [
        TrajectoryEvent(
            timestamp=_event_timestamp(created_at, 0),
            actor="system",
            action="survey_started",
            context={
                "instrumentId": instrument.id,
                "instrumentTitle": instrument.title,
                "numQuestions": len(instrument.questions),
            },
            outcome={"status": "started"},
        )
    ]

    offset = 1
    for index, question in enumerate(instrument.questions, start=1):
        answer = answer_by_id.get(question.id)
        if answer is None and not completed:
            break
        question_context = {
            "instrumentId": instrument.id,
            "questionId": question.id,
            "questionIndex": index,
            "questionType": question.type,
            "construct": question.construct,
        }
        events.append(
            TrajectoryEvent(
                timestamp=_event_timestamp(created_at, offset),
                actor="assistant",
                action="ask_question",
                context=question_context,
                outcome={
                    "prompt": question.prompt,
                    "options": list(question.options),
                },
            )
        )
        offset += 1

        if answer is None:
            continue
        events.append(
            TrajectoryEvent(
                timestamp=_event_timestamp(created_at, offset),
                actor="user",
                action="answer_question",
                context=question_context,
                outcome={
                    "questionId": answer.question_id,
                    "value": answer.value,
                    "rationale": answer.rationale,
                    "confidence": answer.confidence,
                },
            )
        )
        offset += 1

    if completed:
        events.append(
            TrajectoryEvent(
                timestamp=_event_timestamp(created_at, offset),
                actor="system",
                action="survey_completed",
                context={"instrumentId": instrument.id},
                outcome={
                    "numAnswered": len(answers),
                    "missingRequiredQuestionIds": missing_required,
                    "valid": not missing_required,
                },
            )
        )
    return events


def _metrics(answers: List[SurveyAnswer], instrument: SurveyInstrument) -> SurveyMetrics:
    likert_values: List[float] = []
    question_types = {question.id: question.type for question in instrument.questions}
    for answer in answers:
        if question_types.get(answer.question_id) != "likert":
            continue
        try:
            likert_values.append(float(answer.value))
        except (TypeError, ValueError):
            continue
    mean = round(sum(likert_values) / len(likert_values), 2) if likert_values else None
    return SurveyMetrics(
        num_questions=len(instrument.questions),
        num_answered=len(answers),
        mean_likert=mean,
    )
