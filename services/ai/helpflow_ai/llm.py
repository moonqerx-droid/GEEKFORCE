"""Minimal OpenAI-compatible chat client that returns parsed JSON."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen3.5:9b"
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 20.0
DEFAULT_CONNECT_TIMEOUT_SECONDS = 2.0
DEFAULT_OLLAMA_KEEP_ALIVE = "15m"
DEFAULT_OLLAMA_NUM_PREDICT = 320
DEFAULT_OLLAMA_NUM_CTX = 4096
DEFAULT_TEMPERATURE = 0.1
DEFAULT_MAX_RETRIES = 1
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class LLMError(RuntimeError):
    """Any failure to obtain a valid JSON answer from the model."""


@dataclass(frozen=True)
class LLMSettings:
    api_key: str
    provider: str = "openai"
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    keep_alive: str = DEFAULT_OLLAMA_KEEP_ALIVE
    num_predict: int = DEFAULT_OLLAMA_NUM_PREDICT
    num_ctx: int = DEFAULT_OLLAMA_NUM_CTX
    temperature: float = DEFAULT_TEMPERATURE

    @classmethod
    def from_env(cls) -> "LLMSettings | None":
        """None when the LLM is disabled (AI_PROVIDER=mock or no key)."""
        provider = os.getenv("AI_PROVIDER", "mock").strip().lower()
        if provider in ("", "mock", "rules"):
            return None
        if provider == "ollama":
            return cls(
                api_key=os.getenv("AI_API_KEY", "").strip() or "ollama",
                provider="ollama",
                base_url=os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).rstrip("/"),
                model=os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
                timeout=float(os.getenv("AI_TIMEOUT_SECONDS", DEFAULT_OLLAMA_TIMEOUT_SECONDS)),
                connect_timeout=float(os.getenv(
                    "AI_CONNECT_TIMEOUT_SECONDS", DEFAULT_CONNECT_TIMEOUT_SECONDS
                )),
                max_retries=0,
                keep_alive=os.getenv("OLLAMA_KEEP_ALIVE", DEFAULT_OLLAMA_KEEP_ALIVE),
                num_predict=int(os.getenv("OLLAMA_NUM_PREDICT", DEFAULT_OLLAMA_NUM_PREDICT)),
                num_ctx=int(os.getenv("OLLAMA_NUM_CTX", DEFAULT_OLLAMA_NUM_CTX)),
                temperature=float(os.getenv("OLLAMA_TEMPERATURE", DEFAULT_TEMPERATURE)),
            )
        api_key = os.getenv("AI_API_KEY", "").strip()
        if not api_key:
            logger.warning("AI_PROVIDER=%s but AI_API_KEY is empty; using rules only", provider)
            return None
        return cls(
            api_key=api_key,
            base_url=os.getenv("AI_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
            model=os.getenv("AI_MODEL", DEFAULT_MODEL),
            timeout=float(os.getenv("AI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)),
            connect_timeout=float(os.getenv(
                "AI_CONNECT_TIMEOUT_SECONDS", DEFAULT_CONNECT_TIMEOUT_SECONDS
            )),
        )


class LLMClient:
    def __init__(self, settings: LLMSettings, transport: httpx.BaseTransport | None = None):
        self._settings = settings
        self._http = httpx.Client(
            base_url=settings.base_url,
            timeout=httpx.Timeout(settings.timeout, connect=settings.connect_timeout),
            transport=transport,
            headers={"Authorization": f"Bearer {settings.api_key}"},
        )

    @property
    def model(self) -> str:
        return self._settings.model

    @property
    def supports_analysis(self) -> bool:
        """Remote providers classify; local Ollama stays on the faster rules path."""
        return self._settings.provider != "ollama"

    @property
    def supports_response_rendering(self) -> bool:
        """All configured providers may ground a reply in retrieved sources."""
        return True

    @property
    def supports_summaries(self) -> bool:
        """Avoid a second synchronous Ollama call when handing off a ticket."""
        return self._settings.provider != "ollama"

    @property
    def prefers_deterministic_playbooks(self) -> bool:
        """Local models are reserved for company-document answers, not UI polish."""
        return self._settings.provider == "ollama"

    def chat_json(self, system: str, user: str) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        if self._settings.provider == "ollama":
            payload = {
                "model": self._settings.model,
                "stream": False,
                "think": False,
                "format": "json",
                "keep_alive": self._settings.keep_alive,
                "options": {
                    "temperature": self._settings.temperature,
                    "num_predict": self._settings.num_predict,
                    "num_ctx": self._settings.num_ctx,
                },
                "messages": messages,
            }
            request = self._request_ollama
        else:
            payload = {
                "model": self._settings.model,
                "temperature": self._settings.temperature,
                "response_format": {"type": "json_object"},
                "messages": messages,
            }
            request = self._request_openai
        last_error: Exception | None = None
        for attempt in range(self._settings.max_retries + 1):
            try:
                return request(payload)
            except (httpx.HTTPError, LLMError) as error:
                last_error = error
                logger.warning("LLM attempt %d failed: %s", attempt + 1, error)
        raise LLMError(f"LLM unavailable: {last_error}") from last_error

    def _request_openai(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._http.post("/chat/completions", json=payload)
        response.raise_for_status()
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise LLMError("Unexpected response shape") from error
        return parse_json_object(content)

    def _request_ollama(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._http.post("/api/chat", json=payload)
        response.raise_for_status()
        try:
            content = response.json()["message"]["content"]
        except (KeyError, TypeError, ValueError) as error:
            raise LLMError("Unexpected Ollama response shape") from error
        return parse_json_object(content)


def parse_json_object(content: str) -> dict[str, Any]:
    cleaned = _FENCE_RE.sub("", content or "").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise LLMError("Model returned invalid JSON") from error
    if not isinstance(data, dict):
        raise LLMError("Model returned JSON that is not an object")
    return data
