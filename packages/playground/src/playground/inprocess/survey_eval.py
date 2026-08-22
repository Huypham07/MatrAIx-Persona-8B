from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
from playground.model_client import build_json_client
from playground.types import Persona
from playground.user_sim.prompt import render_persona_block


def persona_system_prompt(persona: Persona, *, persona_yaml_path: Optional[str] = None) -> str:
    persona_body = render_persona_block(
        persona, persona_yaml_path=persona_yaml_path
    ).strip()
    if not persona_body:
        persona_body = persona.context or f"I am {persona.name} (Persona ID: {persona.id})."
    return persona_body


def build_survey_task_prompt(*, instrument: SurveyInstrument) -> str:
    lines: list[str] = [
        f"# {instrument.title}",
        "",
        "Please answer all survey questions below based on your persona background and preferences.",
        "",
        "## Questions",
        "",
    ]
    for q in instrument.questions:
        if q.type in {"single_choice", "multi_choice"}:
            if q.option_details:
                opts = ", ".join(f"`{o.id}`: {o.label}" for o in q.option_details)
            else:
                opts = ", ".join(f"`{o}`" for o in q.options)
            lines.append(f"- **[{q.id}]** {q.prompt} (Options: {opts})")
        elif q.type == "likert":
            lines.append(f"- **[{q.id}]** {q.prompt} (Rate integer {q.min_value} to {q.max_value})")
        else:
            lines.append(f"- **[{q.id}]** {q.prompt} (Free text)")

    lines.extend([
        "",
        "## Instructions",
        "- For choice questions, output ONLY the choice id (e.g. \"a\", \"b\", etc.) as the value.",
        "- For likert questions, output the integer rating as the value.",
        "- For free text questions, output a brief 1-sentence response as the value.",
        "- Respond in valid JSON only without markdown explanation.",
        "",
        "## Required JSON Format",
        "```json",
        "{",
        f'  "instrument": {{"id": "{instrument.id}", "title": "{instrument.title}"}},',
        '  "answers": [',
        '    {"questionId": "q0", "value": "a"},',
        '    {"questionId": "q1", "value": "b"}',
        "  ]",
        "}",
        "```",
    ])
    return "\n".join(lines).strip()


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
            persona, persona_yaml_path=persona_yaml_path
        )
        prompts = {
            "personaPrompt": persona_prompt,
            "harborPrompt": persona_prompt,
            "taskPrompt": task_prompt,
        }
        if client is None:
            if client_factory is not None:
                client = client_factory(config.persona_model)
            else:
                client = build_json_client(config.persona_model)

        questions = instrument.questions
        chunk_size = 5 if len(questions) > 5 else len(questions)
        all_answers: list[SurveyAnswer] = []
        total_usage_dict: dict[str, Any] = {}

        for chunk_start in range(0, len(questions), chunk_size):
            chunk_end = min(chunk_start + chunk_size, len(questions))
            chunk = questions[chunk_start:chunk_end]

            chunk_lines = [
                f"# {instrument.title}",
                "",
                f"Please answer questions {chunk_start + 1} to {chunk_end} of {len(questions)} as yourself in JSON.",
                "",
                "## Questions",
                "",
            ]
            for q in chunk:
                if q.type in {"single_choice", "multi_choice"}:
                    if q.option_details:
                        opts = ", ".join(f"`{o.id}`: {o.label}" for o in q.option_details)
                    else:
                        opts = ", ".join(f"`{o}`" for o in q.options)
                    chunk_lines.append(f"- **[{q.id}]** {q.prompt} (Options: {opts})")
                elif q.type == "likert":
                    chunk_lines.append(f"- **[{q.id}]** {q.prompt} (Rate integer {q.min_value} to {q.max_value})")
                else:
                    chunk_lines.append(f"- **[{q.id}]** {q.prompt} (Free text)")

            chunk_lines.extend([
                "",
                "## Instructions",
                "- For choice questions, output ONLY the choice id (e.g. \"a\", \"b\", etc.) as value.",
                "- For likert questions, output integer rating as value.",
                "- For free text questions, output a brief 1-sentence response.",
                "- Respond in valid JSON only.",
                "",
                "## Required JSON Format",
                "```json",
                '{"answers": [{"questionId": "q0", "value": "a"}]}',
                "```",
            ])
            chunk_task_prompt = "\n".join(chunk_lines).strip()

            q_preview = chunk[0].prompt[:60]
            emit({
                "type": "stage",
                "stage": "running_agent",
                "message": f"Answering Q{chunk_start + 1}-Q{chunk_end}/{len(questions)}: {q_preview}...",
            })
            emit({"type": "phase", "phase": "survey_answering"})

            assert_budget_allows_request(job_dir)
            if hasattr(client, "complete_json_with_usage"):
                completion = client.complete_json_with_usage(
                    prompts["personaPrompt"], chunk_task_prompt
                )
                raw = completion.data
                usage = completion.usage
            else:
                raw = client.complete_json(prompts["personaPrompt"], chunk_task_prompt)
                usage = None

            if usage is not None:
                record_trial_cost(job_dir, usage.cost_usd)
                total_usage_dict = usage.to_dict()

            chunk_instrument = SurveyInstrument(
                id=instrument.id,
                title=instrument.title,
                questions=chunk,
                description=instrument.description,
            )
            raw_answers = raw.get("answers") if isinstance(raw, dict) else None
            chunk_norm_answers = _normalize_answers(raw_answers, chunk_instrument)
            for ans in chunk_norm_answers:
                all_answers.append(ans)
                emit({
                    "type": "survey_answer",
                    "questionId": ans.question_id,
                    "value": ans.value,
                    "progress": f"{len(all_answers)}/{len(questions)}",
                    "message": f"Answered [{ans.question_id}]: {ans.value}",
                })

            intermediate_result = SurveyEvalResult(
                config=config,
                persona=persona,
                instrument=instrument,
                answers=list(all_answers),
                trajectory=_build_trajectory(instrument, all_answers, created_at),
                metrics=_metrics(all_answers, instrument),
                created_at=created_at,
                prompts=prompts,
                usage=total_usage_dict or None,
            )
            emit({
                "type": "survey_progress",
                "progress": f"{len(all_answers)}/{len(questions)}",
                "result": intermediate_result.to_dict(),
            })

        answers = all_answers
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
            usage=total_usage_dict or None,
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

        answer = answer_by_id.get(question.id)
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


def _normalize_answers(raw_answers: Any, instrument: SurveyInstrument) -> List[SurveyAnswer]:
    by_id = {question.id: question for question in instrument.questions}
    answers: List[SurveyAnswer] = []
    if not isinstance(raw_answers, list):
        raw_answers = []
    seen = set()
    for raw in raw_answers:
        if not isinstance(raw, dict):
            continue
        answer = SurveyAnswer.from_dict(raw)
        question = by_id.get(answer.question_id)
        if question is None or answer.question_id in seen:
            continue
        answer.value = _normalize_value(answer.value, question)
        if not question.resolves_ask_rationale(instrument):
            answer.rationale = ""
        if not question.resolves_ask_confidence(instrument):
            answer.confidence = None
        answers.append(answer)
        seen.add(answer.question_id)
    for question in instrument.questions:
        if question.required and question.id not in seen:
            answers.append(
                SurveyAnswer(
                    question_id=question.id,
                    value=_default_value(question),
                    rationale=(
                        "No persona-specific answer was produced, so a neutral answer was used."
                        if question.resolves_ask_rationale(instrument)
                        else ""
                    ),
                    confidence=(
                        0.0 if question.resolves_ask_confidence(instrument) else None
                    ),
                )
            )
    return answers


def _normalize_value(value: Any, question: SurveyQuestion) -> Any:
    if question.type == "likert":
        try:
            number = int(round(float(value)))
        except (TypeError, ValueError):
            low = question.min_value or 1
            high = question.max_value or 5
            number = int(round((low + high) / 2))
        return max(question.min_value or 1, min(question.max_value or 5, number))
    if question.type == "single_choice":
        text = str(value)
        return text if text in question.options else question.options[0]
    if question.type == "multi_choice":
        values = value if isinstance(value, list) else [value]
        selected = [str(item) for item in values if str(item) in question.options]
        return selected or [question.options[0]]
    return str(value or "").strip()


def _default_value(question: SurveyQuestion) -> Any:
    if question.type == "likert":
        low = question.min_value or 1
        high = question.max_value or 5
        return int(round((low + high) / 2))
    if question.type == "single_choice":
        return question.options[0]
    if question.type == "multi_choice":
        return [question.options[0]]
    return ""


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
