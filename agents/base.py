from __future__ import annotations

import json
import logging
import os
import re

import requests

log = logging.getLogger("transitai")

DEFAULT_SYSTEM = (
    "You are a transit planning assistant. Reply only with what is asked."
)


class LLMClient:
    def __init__(self):
        self.openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.openai_base = os.getenv(
            "OPENAI_BASE_URL", "https://api.openai.com/v1"
        ).rstrip("/")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.ollama_host = os.getenv("OLLAMA_HOST", "").strip().rstrip("/")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2")

    @property
    def available(self) -> bool:
        return bool(self.openai_key or self.ollama_host)

    @property
    def label(self) -> str:
        if self.openai_key:
            return f"LLM: {self.openai_model} (OpenAI-compatible)"
        if self.ollama_host:
            return f"LLM: {self.ollama_model} (Ollama)"
        return "LLM: not configured — deterministic agents in use"

    def complete(self, user: str, system: str = DEFAULT_SYSTEM) -> str | None:
        try:
            if self.openai_key:
                return self._openai(user, system)
            if self.ollama_host:
                return self._ollama(user, system)
        except Exception as exc:
            log.warning("LLM call failed: %s", exc)
        return None

    def complete_json(self, user: str, system: str = DEFAULT_SYSTEM) -> dict | None:
        raw = self.complete(user, system)
        if not raw:
            return None
        text = raw.strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL)
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _openai(self, user: str, system: str) -> str:
        response = requests.post(
            f"{self.openai_base}/chat/completions",
            headers={"Authorization": f"Bearer {self.openai_key}"},
            json={
                "model": self.openai_model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def _ollama(self, user: str, system: str) -> str:
        response = requests.post(
            f"{self.ollama_host}/api/chat",
            json={
                "model": self.ollama_model,
                "stream": False,
                "options": {"temperature": 0},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]
