from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

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
from playground.types import PlaygroundConfig


_SIDECAR_TASK_PATHS = {
    "finance_openbb": "application/tasks/chat_openbb-corporate-action-honesty",
    "meal_planning_nutrition": "application/tasks/chat_meal-planning-nutrition",
    "acme_support_api": "application/tasks/example-chat-api_support_chatbot",
}


class DirectApplicationSession:
    """Session wrapper for non-RecAI chatbot application adapters."""

    def __init__(self, config: PlaygroundConfig) -> None:
        self.config = config
        self.turns = []
        self._session_id: Optional[str] = None
        self._application = _application_for(config.application_id)
        self._task_config = _load_sidecar_task_config(config.application_id)

    def run_turn_sync(self, message: str) -> Dict[str, Any]:
        response = self._application.send_message(
            session_id=self._session_id,
            message=message,
            title="playground",
            context=config_context(self.config),
            engine=self.config.engine,
            bot_type="chat",
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
        try:
            res = client.complete_json(system=sys_prompt, user=prompt)
            assistant_message = str(res.get("reply") or res.get("assistantMessage") or res.get("message") or "")
        except Exception:
            assistant_message = f"Thank you for your message. I am here to help you with {context or self.default_context}."
        if not assistant_message:
            assistant_message = f"I understand. Let me help you with your {context or self.default_context} request."

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


class HTTPChatbotApplication:
    """HTTP client for task-owned chatbot application sidecars with in-process LLM fallback."""

    def __init__(self, *, application_id: str, default_context: str, base_url: str) -> None:
        self.application_id = application_id
        self.default_context = default_context
        self.base_url = base_url.rstrip("/")
        self._fallback = InProcessLLMChatbotApplication(application_id, default_context)

    def send_message(
        self,
        *,
        session_id: Optional[str],
        message: str,
        title: Optional[str],
        context: str,
        engine: Optional[str],
        bot_type: Optional[str],
    ) -> Dict[str, Any]:
        body = {
            "sessionId": session_id,
            "message": message,
            "title": title,
            "applicationId": self.application_id,
            "applicationContext": context or self.default_context,
            "engine": engine,
            "botType": bot_type,
        }
        try:
            return self._request_json("POST", "/v1/messages", body=body)
        except Exception:
            # Fall back to in-process local LLM assistant if sidecar server is unavailable
            return self._fallback.send_message(
                session_id=session_id,
                message=message,
                title=title,
                context=context,
                engine=engine,
                bot_type=bot_type,
            )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        body: Optional[Dict[str, Any]] = None,
        timeout: float = 5.0,
    ) -> Dict[str, Any]:
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
