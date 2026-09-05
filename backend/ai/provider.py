"""Small provider-neutral interface plus a Qwen REST implementation.

The web UI never receives provider names, credentials, request payloads, or raw
responses.  When no key is configured, callers get ``None`` and retain the
fully deterministic workflow.
"""

from __future__ import annotations

import json
import re
import os
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any

import httpx

from backend.config import (
    LEXPILOT_ENABLE_SEMANTIC_AI,
    LLM_REQUEST_TIMEOUT_SECONDS,
    QWEN_API_BASE,
    QWEN_API_KEY,
    QWEN_ENABLE_THINKING,
    QWEN_MODEL,
)


class AIProviderError(RuntimeError):
    """Raised only inside the optional semantic layer; callers must fall back safely."""


class AIProvider(ABC):
    @abstractmethod
    def generate_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        max_output_tokens: int = 2048,
        thinking_level: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError


class QwenProvider(AIProvider):
    """Call Model Studio's OpenAI-compatible Qwen chat endpoint."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = QWEN_MODEL,
        api_base: str = QWEN_API_BASE,
        enable_thinking: bool = QWEN_ENABLE_THINKING,
        timeout_seconds: float = LLM_REQUEST_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        key = str(api_key or "").strip()
        if not key or key.lower().startswith(("your-", "replace-", "请输入")):
            raise ValueError("A configured API key is required")
        if not re.fullmatch(r"[A-Za-z0-9._-]+", model):
            raise ValueError("Invalid model identifier")
        self._api_key = key
        self._model = model
        self._api_base = api_base.rstrip("/")
        self._enable_thinking = bool(enable_thinking)
        self._timeout = timeout_seconds
        self._transport = transport
        self._client = httpx.Client(
            timeout=self._timeout,
            transport=self._transport,
            follow_redirects=False,
        )

    def generate_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        max_output_tokens: int = 2048,
        thinking_level: str | None = None,
    ) -> dict[str, Any]:
        endpoint = f"{self._api_base}/chat/completions"
        effective_thinking = self._enable_thinking and thinking_level == "high"
        schema_text = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "只输出一个符合以下 JSON Schema 的 JSON 对象，不要输出 Markdown 或解释："
                        f"{schema_text}"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "max_completion_tokens": max(128, min(int(max_output_tokens), 16384)),
            "response_format": {"type": "json_object"},
            "enable_thinking": effective_thinking,
        }
        try:
            response = self._client.post(
                endpoint,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                },
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AIProviderError("Semantic analysis request failed") from exc

        try:
            content = body["choices"][0]["message"]["content"]
            if isinstance(content, list):
                text = "".join(
                    str(part.get("text", "")) if isinstance(part, dict) else str(part)
                    for part in content
                ).strip()
            else:
                text = str(content).strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
            value = json.loads(text)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise AIProviderError("Semantic analysis returned invalid structured data") from exc
        if not isinstance(value, dict):
            raise AIProviderError("Semantic analysis did not return an object")
        return value

    def close(self) -> None:
        self._client.close()


def _configured_key() -> str:
    key = str(QWEN_API_KEY or "").strip()
    if not key or key in {"sk-your-key-here", "your-api-key-here"}:
        return ""
    return key


@lru_cache(maxsize=1)
def get_ai_provider() -> AIProvider | None:
    """Return the configured provider without exposing it to API or Streamlit state."""

    key = _configured_key()
    if not LEXPILOT_ENABLE_SEMANTIC_AI or not key:
        return None
    try:
        return QwenProvider(key)
    except ValueError:
        return None


@lru_cache(maxsize=1)
def get_consultation_provider() -> AIProvider | None:
    """Longer bounded timeout for a multi-step plan, separate from quick intake."""
    key = _configured_key()
    if not LEXPILOT_ENABLE_SEMANTIC_AI or not key:
        return None
    try:
        timeout = max(5.0, min(float(os.getenv('LEXPILOT_CONSULT_TIMEOUT_SECONDS', '30')), 60.0))
        return QwenProvider(key, timeout_seconds=timeout)
    except ValueError:
        return None
