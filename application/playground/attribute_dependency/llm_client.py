"""LLM Client wrapper for Attribute Dependency hierarchical pruning."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

# Automatically load environment variables from .env.local and .env
try:
    from dotenv import load_dotenv

    _repo_root = Path(__file__).resolve().parents[3]
    _playground_root = _repo_root / "application" / "playground"
    for _env_file in [
        _playground_root / ".env.local",
        _playground_root / ".env",
        _repo_root / ".env.local",
        _repo_root / ".env",
    ]:
        if _env_file.exists():
            load_dotenv(_env_file, override=False)
except ImportError:
    pass


class BaseLLMClient(Protocol):
    """Protocol for LLM clients."""

    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Send prompt and return parsed JSON response."""
        ...

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Send prompt and return raw text/free-form response."""
        ...


def build_llm_client_for_model(
    model_name: Optional[str] = None,
    *,
    temperature: float = 0.0,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    auth_header: Optional[str] = None,
    default_headers: Optional[Dict[str, str]] = None,
) -> BaseLLMClient:
    """Unified factory to resolve any model name into the appropriate LLM client."""
    return OpenAILLMClient(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        auth_header=auth_header,
        temperature=temperature,
        default_headers=default_headers,
    )


class OpenAILLMClient:
    """OpenAI-compatible LLM client.

    Supports OpenAI, local servers (vLLM, Ollama, LiteLLM), OpenRouter, DashScope, etc.
    Priority for config:
      1. Explicit constructor arguments / Prefix routing (openrouter/*, local/*, openai/*, dashscope/*)
      2. LOCAL_LLM_* environment variables
      3. OPENROUTER_* / OPENAI_* environment variables
    """

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        auth_header: Optional[str] = None,
        temperature: float = 0.0,
        default_headers: Optional[Dict[str, str]] = None,
    ):
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError(
                "The `openai` package is required to use OpenAILLMClient. "
                "Install it with `pip install openai`."
            ) from e

        raw_model = (model or os.getenv("LOCAL_LLM_MODEL") or "").strip()
        openrouter_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
        local_base = (os.getenv("LOCAL_LLM_BASE_URL") or "").strip()
        openai_base = (os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE") or "").strip()
        dashscope_key = (os.getenv("DASHSCOPE_API_KEY") or "").strip()

        # 1. Prefix: openrouter/...
        if raw_model.startswith("openrouter/"):
            self.model = raw_model.split("/", 1)[1]
            self.base_url = (base_url or os.getenv("OPENROUTER_API_BASE") or os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").strip()
            self.api_key = (api_key or openrouter_key or "dummy-key").strip()
            self.auth_header = auth_header
        # 2. Prefix: local/...
        elif raw_model.startswith("local/"):
            self.model = raw_model.split("/", 1)[1]
            self.base_url = (base_url or local_base or openai_base or "http://203.113.152.4:7777/llm/v1").strip()
            self.auth_header = auth_header or os.getenv("LOCAL_LLM_AUTH_HEADER")
            self.api_key = (api_key or os.getenv("LOCAL_LLM_API_KEY") or "dummy-key").strip()
        # 3. Prefix: dashscope/...
        elif raw_model.startswith("dashscope/"):
            self.model = raw_model.split("/", 1)[1]
            self.base_url = (base_url or os.getenv("DASHSCOPE_API_BASE") or "https://dashscope.aliyuncs.com/compatible-mode/v1").strip()
            self.api_key = (api_key or dashscope_key or "dummy-key").strip()
            self.auth_header = auth_header
        # 4. Prefix: openai/... or standard gpt-
        elif raw_model.startswith("openai/"):
            self.model = raw_model.split("/", 1)[1]
            self.base_url = (base_url or "https://api.openai.com/v1").strip()
            self.api_key = (api_key or os.getenv("OPENAI_API_KEY") or "dummy-key").strip()
            self.auth_header = auth_header
        # 5. Non-prefixed model string
        else:
            if base_url:
                self.base_url = base_url
                self.model = raw_model or "Qwen3-14B"
                self.api_key = (api_key or os.getenv("LOCAL_LLM_API_KEY") or "dummy-key").strip()
                self.auth_header = auth_header or os.getenv("LOCAL_LLM_AUTH_HEADER")
            elif local_base:
                self.base_url = local_base
                self.model = raw_model or "Qwen3-14B"
                self.api_key = (api_key or os.getenv("LOCAL_LLM_API_KEY") or "dummy-key").strip()
                self.auth_header = auth_header or os.getenv("LOCAL_LLM_AUTH_HEADER")
            elif openai_base:
                self.base_url = openai_base
                self.model = raw_model or "Qwen3-14B"
                self.api_key = (api_key or os.getenv("LOCAL_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "dummy-key").strip()
                self.auth_header = auth_header or os.getenv("LOCAL_LLM_AUTH_HEADER")
            elif openrouter_key and ("minimax" in raw_model.lower() or "deepseek" in raw_model.lower() or "free" in raw_model.lower()):
                self.base_url = "https://openrouter.ai/api/v1"
                self.model = raw_model or "minimax/minimax-m3:free"
                self.api_key = (api_key or openrouter_key).strip()
                self.auth_header = auth_header
            else:
                self.base_url = "http://203.113.152.4:7777/llm/v1"
                self.model = raw_model or "Qwen3-14B"
                self.api_key = (api_key or "dummy-key").strip()
                self.auth_header = auth_header or os.getenv("LOCAL_LLM_AUTH_HEADER")

        self.temperature = temperature

        # Build custom headers if auth_header or custom headers are supplied
        headers = dict(default_headers or {})
        if self.auth_header:
            headers["Authorization"] = self.auth_header

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            default_headers=headers if headers else None,
        )

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        enable_thinking: bool = False,
    ) -> str:
        """Call LLM and return raw free text response without JSON constraint."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
        }
        if enable_thinking:
            kwargs["extra_body"] = {
                "chat_template_kwargs": {
                    "enable_thinking": True
                }
            }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    def complete_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Alias for generate_text."""
        return self.generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def complete(self, prompt: str, system_prompt: Optional[str] = None, enable_thinking:bool=False) -> Dict[str, Any]:
        """Call LLM and parse JSON response."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Try with response_format={"type": "json_object"} first; fallback to standard if not supported by local model
        create_kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "timeout": 60,
        }
        if enable_thinking:
            create_kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": True}}
        try:
            response = self.client.chat.completions.create(
                **create_kwargs,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            err_msg = str(e).lower()
            if "response_format" in err_msg or "json_object" in err_msg or "400" in err_msg or "extra_body" in err_msg:
                create_kwargs.pop("extra_body", None)
                response = self.client.chat.completions.create(
                    **create_kwargs,
                )
            else:
                raise e

        content = response.choices[0].message.content or "{}"
        return self._clean_and_parse_json(content)

    @staticmethod
    def _clean_and_parse_json(raw: str) -> Dict[str, Any]:
        """Extract and parse JSON from LLM output."""
        raw = raw.strip()
        if raw.startswith("```json"):
            raw = raw[7:]
        elif raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"(\{.*\})", raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            return {"error": "Failed to parse JSON", "raw": raw}

class MockLLMClient:
    """Mock LLM client for testing and offline development."""

    def __init__(self, *args, **kwargs):
        pass

    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Mock JSON completion returning generic structured response."""
        # Check if this is an adherence judge prompt
        if "Evaluated Persona Attributes" in prompt or "Adherence" in (system_prompt or ""):
            return {
                "question_id": "mock_q",
                "evaluated_attributes": [
                    {
                        "attribute_id": "dospert_financial_risk_tolerance",
                        "attribute_label": "DOSPERT Financial Risk Tolerance",
                        "persona_value": "Very low",
                        "classification": "CONSISTENT",
                        "score": 1.0,
                        "reasoning": "Mock verdict: persona trait consistently justifies the answer.",
                    }
                ],
                "question_summary": "Mock adherence evaluation complete.",
            }
        return {
            "selected_ids": [],
            "selected_attributes": [],
            "reasoning": "Mock response for offline testing.",
        }

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Mock raw text generation."""
        return "This is a mock free text response."

    def complete_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Alias for generate_text."""
        return self.generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )


if __name__ == "__main__":
    client = OpenAILLMClient()
    
    # 1. Free text generation demo
    print("--- Testing Free Text Generation ---")
    text_resp = client.generate_text(
        prompt="Hello world! Introduce yourself in one sentence.",
        system_prompt="You are a helpful assistant.",
    )
    print("Free text output:", text_resp)

    # 2. JSON completion demo
    print("\n--- Testing JSON Completion ---")
    json_resp = client.complete(
        prompt="Introduce yourself and return a JSON object with keys 'greeting' (string) and 'status' (string).",
        system_prompt="You are a helpful assistant. Always respond in valid JSON format.",
    )
    print("JSON output:", json_resp)