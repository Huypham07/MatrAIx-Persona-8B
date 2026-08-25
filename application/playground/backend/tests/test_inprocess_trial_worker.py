"""Focused behavior tests for host-native in-process trial execution."""

from __future__ import annotations

import json
from pathlib import Path

from backend.service.survey_types import (
    SurveyAnswer,
    SurveyEvalResult,
    SurveyInstrument,
    SurveyMetrics,
    SurveyQuestion,
)
from playground.types import (
    MetricScores,
    Persona,
    PlaygroundConfig,
    PlaygroundResult,
    PlaygroundTurn,
    Questionnaire,
)
from playground.user_sim.runner import ConversationNotTerminated

from backend.service.inprocess_trial_worker import run_inprocess_trial


def _write_manifest(tmp_path: Path) -> tuple[Path, Path]:
    persona = tmp_path / "personas" / "p.yaml"
    persona.parent.mkdir(parents=True)
    persona.write_text(
        "persona_id: p\ndisplay_name: Pat\ndimensions:\n  decision_style: analytical\n",
        encoding="utf-8",
    )
    trials = tmp_path / "jobs" / "job"
    manifest = {
        "trial_name": "trial-p",
        "trials_dir": str(trials),
        "task": {"path": "application/tasks/chat_meal-planning-nutrition"},
        "agent": {
            "name": "persona-user-sim",
            "model_name": "test/model",
            "kwargs": {"persona_path": str(persona.relative_to(tmp_path))},
        },
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path, trials / "trial-p"


def _playground_result() -> PlaygroundResult:
    turns = [
        PlaygroundTurn(
            turn_index=index,
            user_message=f"question-{index}",
            assistant_message=f"reply-{index}",
            decision="satisfied" if index == 5 else "continue",
        )
        for index in range(1, 6)
    ]
    return PlaygroundResult(
        config=PlaygroundConfig(min_turns=5, max_turns=8),
        persona=Persona(
            id="p", name="Pat", dimensions={"decision_style": "analytical"}
        ),
        sut_description="Meal assistant",
        transcript=turns,
        questionnaire=Questionnaire(3, "partial", 3, "partial", 3, "mixed", True, "asked"),
        metric_scores=MetricScores(num_turns=5),
        created_at="2026-08-25T00:00:00Z",
    )


def test_chat_worker_persists_actual_runner_result(monkeypatch, tmp_path):
    """Removing the real runner call must prevent its actual transcript persisting."""
    manifest, trial_dir = _write_manifest(tmp_path)
    expected = _playground_result()
    captured = {}

    def fake_run(persona, config, **kwargs):
        captured.update(persona=persona, config=config, kwargs=kwargs)
        return expected

    monkeypatch.setattr(
        "backend.service.inprocess_trial_worker.run_inprocess_chatbot_eval", fake_run
    )

    assert run_inprocess_trial(manifest, {}, repo_root=tmp_path) == 0

    transcript = json.loads((trial_dir / "verifier" / "transcript.json").read_text())
    feedback = json.loads((trial_dir / "verifier" / "user_feedback.json").read_text())
    assert len(transcript["turns"]) == 5
    assert feedback["overallExperienceRating"] == 3
    assert captured["persona"].dimensions["decision_style"] == "analytical"
    assert captured["kwargs"]["persona_yaml_path"] == str(
        (tmp_path / "personas" / "p.yaml").resolve()
    )


def test_survey_worker_persists_each_partial_progress(monkeypatch, tmp_path):
    """Dropping progress persistence would lose truthful completed answers on a crash."""
    manifest, trial_dir = _write_manifest(tmp_path)
    payload = json.loads(manifest.read_text())
    payload["task"]["path"] = "application/tasks/example-survey_product-feedback"
    payload["agent"]["name"] = "persona-json-survey"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    class FakeRunner:
        def __call__(self, persona, instrument, config, **kwargs):
            answers = []
            for question_id, value in (("q1", 4), ("q2", "b")):
                answers.append(SurveyAnswer(question_id=question_id, value=value))
                partial = SurveyEvalResult(
                    config,
                    persona,
                    instrument,
                    list(answers),
                    [],
                    SurveyMetrics(len(instrument.questions), len(answers)),
                    "2026-08-25T00:00:00Z",
                    {},
                )
                kwargs["on_event"](
                    {"type": "survey_answer", "questionId": question_id, "value": value}
                )
                kwargs["on_event"](
                    {"type": "survey_progress", "result": partial.to_dict()}
                )
            return partial

    monkeypatch.setattr(
        "backend.service.inprocess_trial_worker.InprocessSurveyEvalRunner", FakeRunner
    )
    monkeypatch.setattr(
        "backend.service.inprocess_trial_worker.survey_questionnaire_id_for_task_path",
        lambda *_args, **_kwargs: "fixture-survey",
    )
    monkeypatch.setattr(
        "backend.service.inprocess_trial_worker.get_survey_instrument",
        lambda *_args, **_kwargs: SurveyInstrument(
            id="s",
            title="S",
            questions=[
                SurveyQuestion(id="q1", prompt="Rate"),
                SurveyQuestion(
                    id="q2",
                    prompt="Pick",
                    type="single_choice",
                    options=["a", "b"],
                ),
            ],
        ),
    )

    assert run_inprocess_trial(manifest, {}, repo_root=tmp_path) == 0

    events = [
        json.loads(line)
        for line in (trial_dir / "events.jsonl").read_text().splitlines()
    ]
    assert [event["questionId"] for event in events if event["type"] == "survey_answer"] == [
        "q1",
        "q2",
    ]
    assert json.loads((trial_dir / "verifier" / "survey_result.json").read_text())["metrics"]["numAnswered"] == 2


def test_chat_worker_keeps_partial_transcript_without_positive_feedback(monkeypatch, tmp_path):
    """Replacing a terminated conversation with successful feedback is a false completion."""
    manifest, trial_dir = _write_manifest(tmp_path)
    partial = [
        PlaygroundTurn(1, "first", "reply", decision="continue"),
        PlaygroundTurn(2, "second", "reply", decision="continue"),
    ]
    error = ConversationNotTerminated("max_turns_reached", partial)
    monkeypatch.setattr(
        "backend.service.inprocess_trial_worker.run_inprocess_chatbot_eval",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
    )

    assert run_inprocess_trial(manifest, {}, repo_root=tmp_path) == 1

    transcript = json.loads((trial_dir / "verifier" / "transcript.json").read_text())
    result = json.loads((trial_dir / "result.json").read_text())
    assert [turn["userMessage"] for turn in transcript["turns"]] == ["first", "second"]
    assert not (trial_dir / "verifier" / "user_feedback.json").exists()
    assert result["exception_info"]["exception_type"] == "ConversationNotTerminated"


def test_missing_canonical_persona_is_a_failure(tmp_path):
    """Falling back to a generic persona would hide an invalid canonical launch."""
    manifest, trial_dir = _write_manifest(tmp_path)
    payload = json.loads(manifest.read_text())
    payload["agent"]["kwargs"]["persona_path"] = "personas/missing.yaml"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    assert run_inprocess_trial(manifest, {}, repo_root=tmp_path) == 1

    result = json.loads((trial_dir / "result.json").read_text())
    assert result["exception_info"]["exception_type"] == "FileNotFoundError"
    assert "Canonical persona source not found" in result["exception_info"]["exception_message"]


def test_survey_worker_publishes_one_terminal_after_final_artifacts(monkeypatch, tmp_path):
    """Forwarding a runner terminal would expose incomplete artifacts as final."""
    manifest, trial_dir = _write_manifest(tmp_path)
    payload = json.loads(manifest.read_text())
    payload["task"]["path"] = "application/tasks/example-survey_product-feedback"
    payload["agent"]["name"] = "persona-json-survey"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    snapshots = []
    events = []

    class RecordingWriter:
        def append(self, event):
            events.append(dict(event))
            if event.get("type") == "survey_progress":
                progress = json.loads(
                    (trial_dir / "verifier" / "survey_result.json").read_text()
                )
                snapshots.append(("progress", progress["metrics"]["numAnswered"]))
            if event.get("type") == "done":
                snapshots.append(
                    (
                        "done",
                        (trial_dir / "result.json").is_file(),
                        (trial_dir / "verifier" / "survey_result.json").is_file(),
                    )
                )

    class FakeRunner:
        def __call__(self, persona, instrument, config, **kwargs):
            answer = SurveyAnswer(question_id="q1", value=4)
            result = SurveyEvalResult(
                config,
                persona,
                instrument,
                [answer],
                [],
                SurveyMetrics(1, 1),
                "2026-08-25T00:00:00Z",
                {},
            )
            kwargs["on_event"]({"type": "survey_progress", "result": result.to_dict()})
            kwargs["on_event"]({"type": "done", "result": result.to_dict()})
            return result

    monkeypatch.setattr(
        "playground.harbor.trial_events.TrialEventWriter.for_trial_dir",
        lambda *_args: RecordingWriter(),
    )
    monkeypatch.setattr(
        "backend.service.inprocess_trial_worker.InprocessSurveyEvalRunner", FakeRunner
    )
    monkeypatch.setattr(
        "backend.service.inprocess_trial_worker.survey_questionnaire_id_for_task_path",
        lambda *_args, **_kwargs: "fixture-survey",
    )
    monkeypatch.setattr(
        "backend.service.inprocess_trial_worker.get_survey_instrument",
        lambda *_args, **_kwargs: SurveyInstrument(
            id="s", title="S", questions=[SurveyQuestion(id="q1", prompt="Rate")]
        ),
    )

    assert run_inprocess_trial(manifest, {}, repo_root=tmp_path) == 0
    assert snapshots == [("progress", 1), ("done", True, True)]
    assert [event["type"] for event in events].count("done") == 1


def test_chat_failure_persists_pending_observed_pair_before_one_terminal(monkeypatch, tmp_path):
    """A provider error after an assistant event must not discard that real pair."""
    manifest, trial_dir = _write_manifest(tmp_path)
    snapshots = []
    events = []

    class RecordingWriter:
        def append(self, event):
            events.append(dict(event))
            if event.get("type") == "done":
                transcript = json.loads(
                    (trial_dir / "verifier" / "transcript.json").read_text()
                )
                snapshots.append(
                    (
                        (trial_dir / "result.json").is_file(),
                        transcript["turns"],
                        event["status"],
                    )
                )

    def fake_run(*_args, **kwargs):
        kwargs["on_event"]({"type": "user_message", "turnIndex": 1, "message": "Need help"})
        kwargs["on_event"](
            {
                "type": "assistant_message",
                "turnIndex": 1,
                "userMessage": "Need help",
                "assistantMessage": "Tell me more",
                "structuredExposure": [],
            }
        )
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        "playground.harbor.trial_events.TrialEventWriter.for_trial_dir",
        lambda *_args: RecordingWriter(),
    )
    monkeypatch.setattr(
        "backend.service.inprocess_trial_worker.run_inprocess_chatbot_eval", fake_run
    )

    assert run_inprocess_trial(manifest, {}, repo_root=tmp_path) == 1
    assert len([event for event in events if event["type"] == "done"]) == 1
    result = json.loads((trial_dir / "result.json").read_text())
    assert result["terminal_status"] == "failed"
    assert result["succeeded"] is False
    assert snapshots == [
        (
            True,
            [
                {
                    "turnIndex": 1,
                    "userMessage": "Need help",
                    "assistantMessage": "Tell me more",
                    "structuredExposure": [],
                }
            ],
            "failed",
        )
    ]
