import json
import urllib.request
from pathlib import Path

import pytest

from playground.inprocess.chatbot_eval import (
    ApplicationUnavailable,
    DirectApplicationSession,
    HTTPChatbotApplication,
    InProcessLLMChatbotApplication,
    inprocess_chatbot_config,
)
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


def test_survey_events_expose_persona_expected_language(tmp_path):
    client = ScriptedJSONClient(
        [{"answer": {"questionId": "q1", "value": "respuesta libre"}}]
    )
    persona = Persona(
        id="p1",
        name="Persona",
        dimensions={"primary_language": "Spanish", "region": "Latin America"},
    )
    path = tmp_path / "persona_p1.yaml"
    path.write_text(
        "persona_id: p1\ndimensions:\n  primary_language: Spanish\n  region: Latin America\n",
        encoding="utf-8",
    )
    events = []

    InprocessSurveyEvalRunner()(
        persona,
        SurveyInstrument(
            id="s",
            title="S",
            questions=[SurveyQuestion(id="q1", prompt="Explain", type="free_text")],
        ),
        client=client,
        on_event=events.append,
        persona_yaml_path=str(path),
    )

    relevant = [
        event
        for event in events
        if event["type"] in {"survey_question_started", "survey_answer"}
    ]
    assert relevant
    assert all(event["expectedLanguage"] == "Spanish" for event in relevant)


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


def test_survey_retries_parse_error_once_then_returns_valid_answer(tmp_path):
    class ParseErrorClient:
        def __init__(self):
            self.calls = []
            self.responses = [ValueError("invalid JSON response"), {"answer": {"questionId": "q1", "value": 4}}]

        def complete_json(self, system, user):
            self.calls.append({"system": system, "user": user})
            response = self.responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response

    client = ParseErrorClient()
    result = InprocessSurveyEvalRunner()(
        _persona(),
        SurveyInstrument(id="s", title="S", questions=[SurveyQuestion(id="q1", prompt="Rate")]),
        client=client,
        persona_yaml_path=_persona_yaml(tmp_path),
    )

    assert [answer.value for answer in result.answers] == [4]
    assert len(client.calls) == 2
    assert "invalid JSON response" in client.calls[1]["user"]


def test_survey_turns_second_parse_error_into_invalid_response_without_events(tmp_path):
    class ParseErrorClient:
        def __init__(self):
            self.calls = []

        def complete_json(self, system, user):
            self.calls.append({"system": system, "user": user})
            raise ValueError("invalid JSON response")

    client = ParseErrorClient()
    events = []

    with pytest.raises(InvalidSurveyResponse, match="q1") as error:
        InprocessSurveyEvalRunner()(
            _persona(),
            SurveyInstrument(id="s", title="S", questions=[SurveyQuestion(id="q1", prompt="Rate")]),
            client=client,
            on_event=events.append,
            persona_yaml_path=_persona_yaml(tmp_path),
        )

    assert "invalid JSON response" in error.value.detail
    assert isinstance(error.value.__cause__, ValueError)
    assert len(client.calls) == 2
    assert not [event for event in events if event["type"] in {"survey_answer", "survey_progress"}]


def test_survey_progress_trajectory_excludes_future_questions_and_completion(tmp_path):
    events = []
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
        client=ScriptedJSONClient(
            [
                {"answer": {"questionId": "q1", "value": 3}},
                {"answer": {"questionId": "q2", "value": 4}},
            ]
        ),
        on_event=events.append,
        persona_yaml_path=_persona_yaml(tmp_path),
    )

    progress = [event["result"]["trajectory"] for event in events if event["type"] == "survey_progress"]
    assert [event["action"] for event in progress[0]] == [
        "survey_started",
        "ask_question",
        "answer_question",
    ]
    assert [event["action"] for event in progress[1]] == [
        "survey_started",
        "ask_question",
        "answer_question",
        "ask_question",
        "answer_question",
    ]
    assert [event.action for event in result.trajectory] == [
        "survey_started",
        "ask_question",
        "answer_question",
        "ask_question",
        "answer_question",
        "survey_completed",
    ]


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
    monkeypatch.setenv("CHATBOT_REQUEST_TIMEOUT_SECONDS", "42")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    session = DirectApplicationSession(
        PlaygroundConfig(
            application_id="finance_openbb",
            application_context="financial_research",
        )
    )
    turn = session.run_turn_sync("Can you compare low-cost broad market ETFs?")

    assert calls[0]["url"] == "http://finance.local/v1/messages"
    assert calls[0]["timeout"] == 42
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


def test_http_chatbot_retries_temporary_reply_then_returns_real_reply(monkeypatch):
    app = HTTPChatbotApplication(
        application_id="meal_planning_nutrition",
        default_context="meal",
        base_url="http://meal",
    )
    replies = iter(
        [
            {
                "sessionId": "s",
                "reply": "I'm temporarily unable to generate a reply. Please try again in a moment.",
            },
            {"sessionId": "s", "reply": "What foods do you dislike?"},
        ]
    )
    monkeypatch.setattr(app, "_request_json", lambda *_args, **_kwargs: next(replies))

    response = app.send_message(
        session_id=None,
        message="Help",
        title=None,
        context="meal",
        engine=None,
        bot_type="chat",
    )

    assert response["reply"] == "What foods do you dislike?"


def test_http_chatbot_preserves_server_session_across_retry_attempts(monkeypatch):
    app = HTTPChatbotApplication(
        application_id="meal_planning_nutrition",
        default_context="meal",
        base_url="http://meal",
    )
    bodies = []
    replies = iter(
        [
            {
                "sessionId": "server-session",
                "reply": "I'm temporarily unable to generate a reply. Please try again in a moment.",
            },
            {"sessionId": "server-session", "reply": "What foods do you dislike?"},
        ]
    )

    def request(*_args, body, **_kwargs):
        bodies.append(dict(body))
        return next(replies)

    monkeypatch.setattr(app, "_request_json", request)
    monkeypatch.setattr("playground.inprocess.chatbot_eval.time.sleep", lambda *_: None)

    app.send_message(
        session_id=None,
        message="Help",
        title=None,
        context="meal",
        engine=None,
        bot_type="chat",
    )

    assert [body["sessionId"] for body in bodies] == [None, "server-session"]


def test_http_chatbot_emits_retry_events_for_temporary_and_transport_failures(monkeypatch):
    app = HTTPChatbotApplication(
        application_id="meal_planning_nutrition",
        default_context="meal",
        base_url="http://meal",
    )
    events = []
    replies = iter(
        [
            {
                "sessionId": "s",
                "reply": "I'm temporarily unable to generate a reply. Please try again in a moment.",
            },
            {"sessionId": "s", "reply": "A real answer."},
        ]
    )
    monkeypatch.setattr(app, "_request_json", lambda *_args, **_kwargs: next(replies))
    monkeypatch.setattr("playground.inprocess.chatbot_eval.time.sleep", lambda *_: None)

    app.send_message(
        session_id=None,
        message="Help",
        title=None,
        context="meal",
        engine=None,
        bot_type="chat",
        on_event=events.append,
    )

    assert events == [
        {
            "type": "application_retry",
            "attempt": 1,
            "maxAttempts": 3,
            "cause": "temporary_reply",
        }
    ]

    transport_events = []
    monkeypatch.setattr(
        app,
        "_request_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("timed out")),
    )

    with pytest.raises(ApplicationUnavailable, match="timed out"):
        app.send_message(
            session_id=None,
            message="Help",
            title=None,
            context="meal",
            engine=None,
            bot_type="chat",
            on_event=transport_events.append,
        )

    assert [event["type"] for event in transport_events] == [
        "application_retry",
        "application_retry",
        "application_error",
    ]
    assert [event["attempt"] for event in transport_events] == [1, 2, 3]
    assert all(event["maxAttempts"] == 3 for event in transport_events)
    assert all("TimeoutError: timed out" == event["cause"] for event in transport_events)


def test_http_chatbot_persistent_temporary_reply_fails_after_three_attempts(monkeypatch):
    app = HTTPChatbotApplication(
        application_id="meal_planning_nutrition",
        default_context="meal",
        base_url="http://meal",
    )
    calls = []

    def temporary(*_args, **_kwargs):
        calls.append(1)
        return {
            "sessionId": "s",
            "reply": "I'm temporarily unable to generate a reply. Please try again in a moment.",
        }

    monkeypatch.setattr(app, "_request_json", temporary)

    with pytest.raises(ApplicationUnavailable, match="temporary failure"):
        app.send_message(
            session_id=None,
            message="Help",
            title=None,
            context="meal",
            engine=None,
            bot_type="chat",
        )

    assert len(calls) == 3


def test_http_chatbot_persistent_transport_error_fails_after_three_attempts(monkeypatch):
    app = HTTPChatbotApplication(
        application_id="meal_planning_nutrition",
        default_context="meal",
        base_url="http://meal",
    )
    calls = []

    def unavailable(*_args, **_kwargs):
        calls.append(1)
        raise TimeoutError("sidecar timed out")

    monkeypatch.setattr(app, "_request_json", unavailable)

    with pytest.raises(ApplicationUnavailable, match="sidecar timed out"):
        app.send_message(
            session_id=None,
            message="Help",
            title=None,
            context="meal",
            engine=None,
            bot_type="chat",
        )

    assert len(calls) == 3


def test_http_chatbot_blank_reply_fails_after_three_attempts(monkeypatch):
    app = HTTPChatbotApplication(
        application_id="meal_planning_nutrition",
        default_context="meal",
        base_url="http://meal",
    )
    calls = []

    def blank(*_args, **_kwargs):
        calls.append(1)
        return {"sessionId": "s", "reply": ""}

    monkeypatch.setattr(app, "_request_json", blank)

    with pytest.raises(ApplicationUnavailable, match="application unavailable"):
        app.send_message(
            session_id=None,
            message="Help",
            title=None,
            context="meal",
            engine=None,
            bot_type="chat",
        )

    assert len(calls) == 3


def test_inprocess_chatbot_never_replaces_provider_failure_with_canned_reply(monkeypatch):
    class FailingClient:
        def __init__(self):
            self.calls = 0

        def complete_json(self, *_args, **_kwargs):
            self.calls += 1
            raise RuntimeError("model provider unavailable")

    client = FailingClient()
    monkeypatch.setattr(
        "playground.model_client.build_json_client", lambda *_args, **_kwargs: client
    )
    app = InProcessLLMChatbotApplication("meal_planning_nutrition", "meal")

    with pytest.raises(ApplicationUnavailable, match="model provider unavailable"):
        app.send_message(
            session_id=None,
            message="Help",
            title=None,
            context="meal",
            engine=None,
            bot_type="chat",
        )

    assert client.calls == 3


def test_inprocess_chatbot_config_uses_task_minimum_turns(tmp_path):
    input_dir = tmp_path / "application" / "tasks" / "chat_test" / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "chatbot.yaml").write_text(
        "runtimeDefaults:\n  minTurns: 6\n  maxTurns: 8\n",
        encoding="utf-8",
    )

    config = inprocess_chatbot_config(
        "application/tasks/chat_test",
        repo_root=tmp_path,
        env={},
        model_name="local/test-model",
    )

    assert config.min_turns == 6
    assert config.max_turns == 8


def test_inprocess_chatbot_config_defaults_to_eight_maximum_turns(tmp_path):
    config = inprocess_chatbot_config(
        "application/tasks/chat_test",
        repo_root=tmp_path,
        env={},
        model_name="local/test-model",
    )

    assert config.min_turns == 5
    assert config.max_turns == 8
