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


class OpenAILLMClient:
    """OpenAI-compatible LLM client.

    Supports OpenAI, local servers (vLLM, Ollama, LiteLLM), OpenRouter, etc.
    Priority for config:
      1. Explicit constructor arguments
      2. LOCAL_LLM_* environment variables (LOCAL_LLM_MODEL, LOCAL_LLM_BASE_URL, LOCAL_LLM_AUTH_HEADER)
      3. OPENAI_* / LLM_* environment variables
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

        # Resolve model name
        self.model = (
            model
            or os.getenv("LOCAL_LLM_MODEL")
            or os.getenv("OPENAI_MODEL")
            or os.getenv("MATRIX_PERSONA_MODEL")
            or "gpt-4o-mini"
        )

        # Resolve base URL
        self.base_url = (
            base_url
            or os.getenv("LOCAL_LLM_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or os.getenv("LLM_BASE_URL")
        )

        # Resolve auth header & api key
        self.auth_header = (
            auth_header
            or os.getenv("LOCAL_LLM_AUTH_HEADER")
        )

        self.api_key = (
            api_key
            or self.auth_header
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("LLM_API_KEY")
            or "dummy-key"
        )

        self.temperature = temperature

        # Build custom headers if LOCAL_LLM_AUTH_HEADER or custom headers are supplied
        headers = dict(default_headers or {})
        if self.auth_header:
            headers["Authorization"] = self.auth_header

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            default_headers=headers if headers else None,
        )

    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Call LLM and parse JSON response."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Try with response_format={"type": "json_object"} first; fallback to standard if not supported by local model
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            err_msg = str(e).lower()
            if "response_format" in err_msg or "json_object" in err_msg or "400" in err_msg:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
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
    """Mock LLM client for offline development, dry-runs, and deterministic tests."""

    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Return simulated decisions based on keywords in the prompt."""
        prompt_lower = prompt.lower()

        # Check for Layer 1 filter
        if "layer 1 groups" in prompt_lower or "layer 1" in prompt_lower:
            selected = ["background", "capability"]
            if any(k in prompt_lower for k in ["feel", "stress", "personality", "mbti", "attitude", "decision"]):
                selected.append("psychology")
            if any(k in prompt_lower for k in ["routine", "habit", "tool", "work", "ai", "coding"]):
                selected.append("behavior_interaction")
            if any(k in prompt_lower for k in ["hobby", "sport", "health", "diet", "lifestyle"]):
                selected.append("lifestyle_health")
            return {
                "selected_ids": list(set(selected)),
                "reasoning": "Selected groups containing relevant demographic, capability, and behavioral traits."
            }

        # Check for Layer 2 filter
        if "layer 2 subgroups" in prompt_lower or "layer 2" in prompt_lower:
            selected = []
            if "demographics" in prompt_lower:
                selected.append("demographics")
            if "education" in prompt_lower:
                selected.append("education")
            if "career" in prompt_lower:
                selected.append("career")
            if "domains" in prompt_lower:
                selected.append("domains")
            if "skills" in prompt_lower:
                selected.append("skills")
            if "technology_use" in prompt_lower:
                selected.append("technology_use")
            if "work_practices" in prompt_lower:
                selected.append("work_practices")
            if not selected:
                # Default fallback
                selected = ["demographics", "career", "skills", "technology_use"]
            return {
                "selected_ids": selected,
                "reasoning": "Subgroups chosen based on topical relevance to the survey question."
            }

        # Check for Layer 3 filter
        if "layer 3 categories" in prompt_lower or "layer 3" in prompt_lower:
            selected = []
            if "core_demographics" in prompt_lower:
                selected.append("core_demographics")
            if "career_profile" in prompt_lower:
                selected.append("career_profile")
            if "industry" in prompt_lower:
                selected.append("industry")
            if "programming" in prompt_lower:
                selected.append("programming")
            if "developer_ai_tool_adoption" in prompt_lower:
                selected.append("developer_ai_tool_adoption")
            if not selected:
                selected = ["core_demographics", "career_profile"]
            return {
                "selected_ids": selected,
                "reasoning": "Specific categories selected for leaf evaluation."
            }

        # Check for Layer 4 Dimension filter
        if "candidate dimensions" in prompt_lower or "dimensions" in prompt_lower:
            return {
                "selected_attributes": [
                    {
                        "id": "age_bracket",
                        "reasoning": "Age strongly influences adoption and user perspective.",
                        "relevance_strength": "high"
                    },
                    {
                        "id": "years_of_experience",
                        "reasoning": "Seniority and experience correlate with question responses.",
                        "relevance_strength": "high"
                    },
                    {
                        "id": "primary_role",
                        "reasoning": "Job role determines domain context and requirements.",
                        "relevance_strength": "medium"
                    }
                ],
                "reasoning": "Evaluated candidate dimensions against survey question context."
            }

        return {"selected_ids": [], "reasoning": "Generic response"}
