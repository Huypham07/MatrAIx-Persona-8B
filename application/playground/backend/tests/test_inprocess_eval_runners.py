import json
import urllib.request
from pathlib import Path

import pytest

from playground.inprocess.chatbot_eval import DirectApplicationSession
from playground.inprocess.survey_eval import (
    InvalidSurveyResponse,
    InprocessSurveyEvalRunner,
)
from playground.llm_usage import JsonCompletion, LlmUsage
from backend.service.survey_types import SurveyEvalConfig, SurveyInstrument, SurveyQuestion
from playground.types import Persona, PlaygroundConfig


class FakeJSONClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def complete_json(self, system, user):
        self.calls.append((system, user))
        return self.payload


class ScriptedJSONClient:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def complete_json(self, system, user):
        self.calls.append({"system": system, "user": user})
        return self.payloads.pop(0)


def _persona():
    return Persona(
        id="p1",
        name="Persona One",
    )


def _persona_yaml(tmp_path: Path) -> str:
    path = tmp_path / "persona_p1.yaml"
    path.write_text(
        "\n".join(
            [
                "persona_id: 'p1'",
                "version: '1.0'",
                "dimensions:",
                "  age_bracket: 25-34",
                "  region: North America",
                "  gender_identity: Woman",
                "  socioeconomic_band: Middle",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return str(path)


def test_inprocess_survey_runner_returns_result_and_prompts(monkeypatch, tmp_path):
    client = FakeJSONClient(
        {
            "answer": {
                "questionId": "fit",
                "value": 5,
                "rationale": "It fits the persona's needs.",
                "confidence": 0.9,
            }
        }
    )
    monkeypatch.setattr(
        "playground.inprocess.survey_eval.build_json_client",
        lambda model: client,
    )
    instrument = SurveyInstrument(
        id="survey1",
        title="Survey",
        description="A survey about a concrete feature.",
        ask_rationale=True,
        ask_confidence=True,
        questions=[SurveyQuestion(id="fit", prompt="This fits me.")],
    )

    result = InprocessSurveyEvalRunner()(
        _persona(),
        instrument,
        SurveyEvalConfig(persona_model="openai/gpt-4o-mini"),
        created_at="2026-06-26T00:00:00Z",
        persona_yaml_path=_persona_yaml(tmp_path),
    )

    assert result.config.mode == "inprocess_persona_survey"
    assert result.answers[0].question_id == "fit"
    assert result.metrics.num_answered == 1
    assert result.prompts["personaPrompt"]
    assert result.prompts["taskPrompt"]
    assert "## Task instruction" in result.prompts["taskPrompt"]
    assert "## Questionnaire" in result.prompts["taskPrompt"]
    assert "This fits me." in result.prompts["taskPrompt"]
    assert [event.action for event in result.trajectory] == [
        "survey_started",
        "ask_question",
        "answer_question",
        "survey_completed",
    ]
    assert [event.actor for event in result.trajectory] == [
        "system",
        "assistant",
        "user",
        "system",
    ]
    assert result.trajectory[1].context == {
        "instrumentId": "survey1",
        "questionId": "fit",
        "questionIndex": 1,
        "questionType": "likert",
        "construct": "",
    }
    assert result.trajectory[1].outcome["prompt"] == "This fits me."
    assert result.trajectory[2].outcome == {
        "questionId": "fit",
        "value": 5,
        "rationale": "It fits the persona's needs.",
        "confidence": 0.9,
    }
    assert result.trajectory[-1].outcome == {
        "numAnswered": 1,
        "missingRequiredQuestionIds": [],
        "valid": True,
    }
    assert client.calls


def test_survey_calls_model_once_per_question_and_streams_in_order(tmp_path):
    client = ScriptedJSONClient(
        [
            {"answer": {"questionId": "q1", "value": 4}},
            {"answer": {"questionId": "q2", "value": "b"}},
        ]
    )
    instrument = SurveyInstrument(
        id="s",
        title="S",
        questions=[
            SurveyQuestion(
                id="q1", prompt="Rate", type="likert", min_value=1, max_value=5
            ),
            SurveyQuestion(
                id="q2", prompt="Pick", type="single_choice", options=["a", "b"]
            ),
        ],
    )
    events = []

    result = InprocessSurveyEvalRunner()(
        _persona(),
        instrument,
        client=client,
        on_event=events.append,
        persona_yaml_path=_persona_yaml(tmp_path),
    )

    assert len(client.calls) == 2
    assert [answer.value for answer in result.answers] == [4, "b"]
    assert [event["type"] for event in events if event["type"].startswith("survey_")] == [
        "survey_question_started",
        "survey_answer",
        "survey_progress",
        "survey_question_started",
        "survey_answer",
        "survey_progress",
    ]


def test_invalid_choice_retries_once_then_fails_without_first_option(tmp_path):
    client = ScriptedJSONClient(
        [
            {"answer": {"questionId": "q1", "value": "bad"}},
            {"answer": {"questionId": "q1", "value": "still-bad"}},
        ]
    )

    with pytest.raises(InvalidSurveyResponse, match="q1"):
        InprocessSurveyEvalRunner()(
            _persona(),
            SurveyInstrument(
                id="s",
                title="S",
                questions=[
                    SurveyQuestion(
                        id="q1",
                        prompt="Pick",
                        type="single_choice",
                        options=["a", "b"],
                    )
                ],
            ),
            client=client,
            persona_yaml_path=_persona_yaml(tmp_path),
        )

    assert len(client.calls) == 2
    assert "not one of" in client.calls[1]["user"]


def test_survey_merges_usage_across_question_completions(tmp_path):
    class UsageClient(ScriptedJSONClient):
        def complete_json_with_usage(self, system, user):
            payload = self.complete_json(system, user)
            return JsonCompletion(
                data=payload,
                usage=LlmUsage(
                    n_input_tokens=10,
                    n_output_tokens=2,
                    cost_usd=0.01,
                    model="test-model",
                    provider="test",
                ),
            )

    result = InprocessSurveyEvalRunner()(
        _persona(),
        SurveyInstrument(
            id="s",
            title="S",
            questions=[
                SurveyQuestion(id="q1", prompt="Rate"),
                SurveyQuestion(id="q2", prompt="Rate again"),
            ],
        ),
        client=UsageClient(
            [
                {"answer": {"questionId": "q1", "value": 3}},
                {"answer": {"questionId": "q2", "value": 4}},
            ]
        ),
        persona_yaml_path=_persona_yaml(tmp_path),
    )

    assert result.usage == {
        "n_input_tokens": 20,
        "n_output_tokens": 4,
        "cost_usd": 0.02,
        "model": "test-model",
        "provider": "test",
        "cost_source": "estimated",
    }


class FakeHTTPResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_direct_finance_session_uses_http_sidecar(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(
            {
                "url": request.full_url,
                "timeout": timeout,
                "body": json.loads(request.data.decode("utf-8")),
            }
        )
        return FakeHTTPResponse(
            {
                "sessionId": "fin_ses_1",
                "reply": "I can compare ETFs and risk constraints.",
                "turn": {
                    "turnId": "fin_turn_1",
                    "conversationId": "fin_ses_1",
                    "backend": "finance_openbb",
                    "assistantMessage": "I can compare ETFs and risk constraints.",
                    "recommendedItems": [
                        {
                            "itemId": "finance:openbb:etf_search:0",
                            "title": "ETF data",
                        }
                    ],
                },
            }
        )

    monkeypatch.setenv("CHATBOT_UPSTREAM_FINANCE", "http://finance.local")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    session = DirectApplicationSession(
        PlaygroundConfig(
            application_id="finance_openbb",
            application_context="financial_research",
        )
    )
    turn = session.run_turn_sync("Can you compare low-cost broad market ETFs?")

    assert calls[0]["url"] == "http://finance.local/v1/messages"
    assert calls[0]["body"]["applicationId"] == "finance_openbb"
    assert calls[0]["body"]["applicationContext"] == "financial_research"
    assert calls[0]["body"]["message"] == "Can you compare low-cost broad market ETFs?"
    assert turn["assistantMessage"] == "I can compare ETFs and risk constraints."
    assert isinstance(turn.get("structuredExposure"), list)


def test_direct_meal_planning_session_uses_http_sidecar(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(json.loads(request.data.decode("utf-8")))
        return FakeHTTPResponse(
            {
                "sessionId": "med_ses_1",
                "reply": "I can help plan meals around your nutrition goals.",
                "turn": {
                    "turnId": "med_turn_1",
                    "conversationId": "med_ses_1",
                    "backend": "meal_planning_nutrition",
                    "assistantMessage": "I can help plan meals around your nutrition goals.",
                    "recommendedItems": [],
                },
            }
        )

    monkeypatch.setenv("CHATBOT_API_URL", "http://meal.local")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    session = DirectApplicationSession(
        PlaygroundConfig(
            application_id="meal_planning_nutrition",
            application_context="meal_planning",
        )
    )
    turn = session.run_turn_sync("Can you suggest a high-protein dinner?")

    assert calls[0]["applicationId"] == "meal_planning_nutrition"
    assert calls[0]["applicationContext"] == "meal_planning"
    assert turn["assistantMessage"].startswith("I can help plan meals")
