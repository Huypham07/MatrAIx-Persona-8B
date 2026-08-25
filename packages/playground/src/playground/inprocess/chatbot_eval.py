from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

try:
    from fastapi import HTTPException
except ModuleNotFoundError:  # pragma: no cover - test env fallback
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str) -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

from playground.chatbot_task_config import (
    load_chatbot_task_config_for_task_path,
)
from playground.structured_exposure import build_structured_exposure
from playground.task_content_bundle import load_task_content_bundle_for_task_path
from playground.types import Persona, PlaygroundConfig, PlaygroundResult


_SIDECAR_TASK_PATHS = {
    "finance_openbb": "application/tasks/chat_openbb-corporate-action-honesty",
    "meal_planning_nutrition": "application/tasks/chat_meal-planning-nutrition",
    "acme_support_api": "application/tasks/example-chat-api_support_chatbot",
}

_MAX_APPLICATION_ATTEMPTS = 3
_TEMPORARY_REPLY_MARKERS = (
    "temporarily unable",
    "temporary failure",
    "please try again in a moment",
)


class ApplicationUnavailable(RuntimeError):
    """The task-owned chatbot did not return a meaningful reply."""


def _reply_from_response(response: Mapping[str, Any]) -> str:
    turn = response.get("turn")
    turn_data = turn if isinstance(turn, Mapping) else {}
    return str(
        turn_data.get("assistantMessage")
        or turn_data.get("assistantReply")
        or response.get("reply")
        or response.get("assistantMessage")
        or ""
    ).strip()


def _is_temporary_reply(reply: str) -> bool:
    normalized = reply.casefold()
    return not normalized or any(marker in normalized for marker in _TEMPORARY_REPLY_MARKERS)


def _retry_meaningful_reply(
    send: Callable[[], Dict[str, Any]],
    *,
    on_event: Callable[[Dict[str, Any]], None] | None = None,
) -> Dict[str, Any]:
    last_error: Exception | None = None
    temporary_reply = False
    for attempt in range(_MAX_APPLICATION_ATTEMPTS):
        cause = ""
        try:
            response = send()
            reply = _reply_from_response(response)
            if not _is_temporary_reply(reply):
                return response
            temporary_reply = bool(reply)
            cause = "temporary_reply" if reply else "blank_reply"
            last_error = ApplicationUnavailable(
                "temporary failure reply: {}".format(reply or "blank reply")
            )
        except Exception as exc:
            last_error = exc
            cause = "{}: {}".format(type(exc).__name__, exc)
        event_type = (
            "application_error"
            if attempt == _MAX_APPLICATION_ATTEMPTS - 1
            else "application_retry"
        )
        if on_event is not None:
            on_event(
                {
                    "type": event_type,
                    "attempt": attempt + 1,
                    "maxAttempts": _MAX_APPLICATION_ATTEMPTS,
                    "cause": cause,
                }
            )
        if attempt < _MAX_APPLICATION_ATTEMPTS - 1:
            time.sleep(0.05 * (attempt + 1))
    if temporary_reply:
        detail = "temporary failure after {} attempts".format(_MAX_APPLICATION_ATTEMPTS)
    else:
        detail = "application unavailable after {} attempts".format(
            _MAX_APPLICATION_ATTEMPTS
        )
    if last_error is not None:
        detail = "{}: {}".format(detail, last_error)
    raise ApplicationUnavailable(detail) from last_error


class DirectApplicationSession:
    """Session wrapper for non-RecAI chatbot application adapters."""

    def __init__(
        self,
        config: PlaygroundConfig,
        *,
        on_event: Callable[[Dict[str, Any]], None] | None = None,
    ) -> None:
        self.config = config
        self.turns = []
        self._session_id: Optional[str] = None
        self._application = _application_for(config.application_id)
        self._task_config = _load_sidecar_task_config(config.application_id)
        self._on_event = on_event

    def run_turn_sync(self, message: str) -> Dict[str, Any]:
        response = self._application.send_message(
            session_id=self._session_id,
            message=message,
            title="playground",
            context=config_context(self.config),
            engine=self.config.engine,
            bot_type="chat",
            on_event=self._on_event,
        )
        self._session_id = str(response["sessionId"])
        turn = dict(response.get("turn") or {})
        assistant = str(
            turn.get("assistantMessage")
            or turn.get("assistantReply")
            or response.get("reply")
            or ""
        )
        merged = {**response, **turn, "userMessage": message}
        exposure = build_structured_exposure(
            merged,
            self._task_config.structured_exposure if self._task_config else None,
        )
        view = {
            "assistantMessage": assistant,
            "userMessage": message,
            "structuredExposure": exposure,
        }
        self.turns.append(view)
        return view


def inprocess_chatbot_config(
    task_path: str,
    *,
    repo_root: Path,
    env: Mapping[str, str],
    model_name: str,
) -> PlaygroundConfig:
    """Resolve direct-session settings from task metadata and launch settings."""
    task_config = load_chatbot_task_config_for_task_path(
        task_path,
        repo_root=repo_root,
    )
    runtime = task_config.runtime_defaults if task_config is not None else None
    folder = Path(task_path.replace("\\", "/")).name
    fallback_id = folder.replace("chat_", "").replace("-", "_") or "chatbot"
    max_turns_raw = str(env.get("MATRIX_CHATBOT_MAX_TURNS") or "").strip()
    try:
        max_turns = max(1, int(max_turns_raw)) if max_turns_raw else None
    except ValueError:
        max_turns = None
    if max_turns is None and runtime is not None:
        max_turns = runtime.max_turns
    if max_turns is None:
        max_turns = 8
    application_id = (
        str(env.get("MATRIX_CHATBOT_APPLICATION_ID") or "").strip()
        or (runtime.application_id if runtime is not None else "")
        or fallback_id
    )
    application_context = (
        str(env.get("MATRIX_CHATBOT_APPLICATION_CONTEXT") or "").strip()
        or (runtime.application_context if runtime is not None else "")
        or application_id
    )
    domain = (
        str(env.get("MATRIX_CHATBOT_DOMAIN") or "").strip()
        or (runtime.domain if runtime is not None else "")
        or application_context
    )
    return PlaygroundConfig(
        domain=domain,
        application_id=application_id,
        application_context=application_context,
        engine=str(env.get("MATRIX_CHATBOT_ENGINE") or "gpt-4o-mini"),
        persona_model=model_name,
        min_turns=(runtime.min_turns if runtime and runtime.min_turns is not None else 5),
        max_turns=max_turns,
    )


def run_inprocess_chatbot_eval(
    persona: Persona,
    config: PlaygroundConfig,
    *,
    task_path: str,
    persona_yaml_path: str,
    repo_root: Path,
    created_at: str,
    on_event: Callable[[Dict[str, Any]], None] | None = None,
    job_dir: Path | None = None,
) -> PlaygroundResult:
    """Run the canonical UserSim session loop against an in-process app session."""
    from playground.user_sim.runner import run_playground

    task_bundle = load_task_content_bundle_for_task_path(
        task_path,
        repo_root=repo_root,
    )
    sut_description = (
        task_bundle.context_markdown
        or task_bundle.instruction_markdown
        or config.application_context
        or config.domain
    )
    return run_playground(
        DirectApplicationSession(config, on_event=on_event),
        persona,
        sut_description,
        config,
        created_at=created_at,
        on_event=on_event,
        task_path=task_path,
        persona_yaml_path=persona_yaml_path,
        repo_root=repo_root,
        job_dir=job_dir,
    )


def _load_sidecar_task_config(application_id: str):
    task_path = _SIDECAR_TASK_PATHS.get(application_id)
    if not task_path:
        return None
    repo_root = Path(__file__).resolve().parents[4]
    return load_chatbot_task_config_for_task_path(task_path, repo_root=repo_root)


def config_context(config: PlaygroundConfig) -> str:
    return config.application_context or config.domain


def _application_for(application_id: str) -> Any:
    norm = application_id.replace("chat_", "").replace("survey_", "").replace("-", "_")
    if norm in {"finance_openbb", "openbb_corporate_action_honesty"}:
        return HTTPChatbotApplication(
            application_id="finance_openbb",
            default_context="financial_research",
            base_url=_sidecar_base_url(
                "CHATBOT_UPSTREAM_FINANCE",
                "FINANCE_CHATBOT_URL",
                "http://127.0.0.1:8901",
            ),
        )
    if norm in {"meal_planning_nutrition", "meal_planning"}:
        return HTTPChatbotApplication(
            application_id="meal_planning_nutrition",
            default_context="meal_planning",
            base_url=_sidecar_base_url(
                "CHATBOT_API_URL",
                "",
                "http://127.0.0.1:8905",
            ),
        )
    if norm in {"acme_support_api", "support_chatbot", "api_support_chatbot", "mcp_support_chatbot"}:
        return HTTPChatbotApplication(
            application_id="acme_support_api",
            default_context="customer_support",
            base_url=_sidecar_base_url(
                "CHATBOT_API_URL",
                "",
                "http://127.0.0.1:8904",
            ),
        )
    return InProcessLLMChatbotApplication(application_id=norm, default_context=norm)


def _sidecar_base_url(primary_env: str, legacy_env: str, default: str) -> str:
    return (
        os.environ.get(primary_env)
        or os.environ.get(legacy_env)
        or os.environ.get("CHATBOT_API_URL")
        or default
    )


class InProcessLLMChatbotApplication:
    """In-process LLM-backed SUT for chatbot evaluation without external containers."""

    def __init__(self, application_id: str, default_context: str) -> None:
        self.application_id = application_id
        self.default_context = default_context
        self._system_prompts = {
            "meal_planning_nutrition": (
                "You are an expert nutritionist and meal planning assistant. "
                "Help the user plan balanced, delicious, and budget-friendly meals according to their dietary preferences and constraints."
            ),
            "finance_openbb": (
                "You are a financial analyst assistant powered by OpenBB. "
                "Help the user analyze corporate actions, stock fundamentals, and financial statements accurately."
            ),
            "acme_support_api": (
                "You are a helpful and polite ACME customer support assistant. "
                "Assist the user with their product questions, returns, and account inquiries."
            ),
            "acme_support_mcp": (
                "You are a helpful and polite ACME customer support assistant. "
                "Assist the user with their product questions, returns, and account inquiries."
            ),
        }

    def send_message(
        self,
        *,
        session_id: Optional[str],
        message: str,
        title: Optional[str],
        context: str,
        engine: Optional[str],
        bot_type: Optional[str],
        on_event: Callable[[Dict[str, Any]], None] | None = None,
    ) -> Dict[str, Any]:
        import uuid
        from playground.model_client import build_json_client

        session_id = session_id or str(uuid.uuid4())
        sys_prompt = self._system_prompts.get(
            self.application_id,
            f"You are a helpful AI chatbot assistant specialized in {context or self.default_context}."
        )
        client = build_json_client("local/qwen3-14b")
        prompt = (
            f"User message: {message}\n\n"
            f"Domain/Context: {context or self.default_context}\n\n"
            "Generate a conversational assistant response in character. Return JSON: {\"reply\": \"<your response>\"}"
        )

        def send() -> Dict[str, Any]:
            response = client.complete_json(system=sys_prompt, user=prompt)
            assistant_message = str(
                response.get("reply")
                or response.get("assistantMessage")
                or response.get("message")
                or ""
            ).strip()
            return {
                "sessionId": session_id,
                "turn": {
                    "assistantMessage": assistant_message,
                    "userMessage": message,
                },
                "reply": assistant_message,
                "assistantMessage": assistant_message,
                "status": "ok",
            }

        return _retry_meaningful_reply(send, on_event=on_event)


class HTTPChatbotApplication:
    """HTTP client for task-owned chatbot application sidecars."""

    def __init__(self, *, application_id: str, default_context: str, base_url: str) -> None:
        self.application_id = application_id
        self.default_context = default_context
        self.base_url = base_url.rstrip("/")

    def send_message(
        self,
        *,
        session_id: Optional[str],
        message: str,
        title: Optional[str],
        context: str,
        engine: Optional[str],
        bot_type: Optional[str],
        on_event: Callable[[Dict[str, Any]], None] | None = None,
    ) -> Dict[str, Any]:
        active_session_id = session_id

        def send() -> Dict[str, Any]:
            nonlocal active_session_id
            body = {
                "sessionId": active_session_id,
                "message": message,
                "title": title,
                "applicationId": self.application_id,
                "applicationContext": context or self.default_context,
                "engine": engine,
                "botType": bot_type,
            }
            response = self._request_json("POST", "/v1/messages", body=body)
            issued_session_id = str(response.get("sessionId") or "").strip()
            if issued_session_id:
                active_session_id = issued_session_id
            return response

        return _retry_meaningful_reply(
            send,
            on_event=on_event,
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        body: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        if timeout is None:
            try:
                timeout = float(os.environ.get("CHATBOT_REQUEST_TIMEOUT_SECONDS", "90"))
            except ValueError:
                timeout = 90.0
        url = "{}{}".format(self.base_url, path)
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(
                {key: value for key, value in body.items() if value is not None}
            ).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise HTTPException(status_code=exc.code, detail=detail) from exc
        except (TimeoutError, urllib.error.URLError) as exc:
            upstream_hint = {
                "finance_openbb": "CHATBOT_UPSTREAM_FINANCE",
                "meal_planning_nutrition": "CHATBOT_API_URL",
                "acme_support_api": "CHATBOT_API_URL",
            }.get(self.application_id, "CHATBOT_API_URL")
            raise HTTPException(
                status_code=503,
                detail=(
                    "{} sidecar unavailable at {}. Start the chatbot sidecar "
                    "or set {}."
                ).format(
                    self.application_id,
                    self.base_url,
                    upstream_hint,
                ),
            ) from exc
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=502,
                detail="{} sidecar returned invalid JSON".format(self.application_id),
            ) from exc
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=502,
                detail="{} sidecar returned non-object JSON".format(self.application_id),
            )
        return payload
