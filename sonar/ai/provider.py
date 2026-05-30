from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import google.generativeai as genai
from google.api_core.exceptions import GoogleAPICallError, ResourceExhausted

from sonar.config import settings


@dataclass(frozen=True)
class AIResult:
    raw_response: str | None
    parsed_json: dict[str, Any] | None
    status: str
    error: str | None = None


class AIProvider:
    provider_name = "base"
    model_name = "none"
    enabled = False

    def generate_json(self, prompt: str, schema_name: str) -> AIResult:
        raise NotImplementedError


class GeminiProvider(AIProvider):
    provider_name = "gemini"

    def __init__(self) -> None:
        self.enabled = bool(settings.gemini_api_key)
        self.model_name = settings.gemini_model
        if self.enabled:
            genai.configure(api_key=settings.gemini_api_key)
            self.model = genai.GenerativeModel(settings.gemini_model)
        else:
            self.model = None

    def generate_json(self, prompt: str, schema_name: str) -> AIResult:
        if not self.enabled or not self.model:
            return AIResult(None, None, "skipped", "provider_disabled")

        try:
            response = self.model.generate_content(prompt)
            raw_text = response.text.strip()
        except ResourceExhausted as exc:
            return AIResult(None, None, "failed", f"quota_exceeded: {exc}")
        except GoogleAPICallError as exc:
            return AIResult(None, None, "failed", f"api_error: {exc}")
        except Exception as exc:
            return AIResult(None, None, "failed", f"unexpected_error: {exc}")

        try:
            return AIResult(raw_text, json.loads(normalize_json_text(raw_text)), "complete")
        except json.JSONDecodeError:
            return AIResult(raw_text, None, "failed", "invalid_json")


class FakeProvider(AIProvider):
    provider_name = "fake"
    model_name = "fake-json"
    enabled = True

    def __init__(self, payload: dict[str, Any] | str):
        self.payload = payload

    def generate_json(self, prompt: str, schema_name: str) -> AIResult:
        if isinstance(self.payload, str):
            try:
                return AIResult(self.payload, json.loads(normalize_json_text(self.payload)), "complete")
            except json.JSONDecodeError:
                return AIResult(self.payload, None, "failed", "invalid_json")
        raw = json.dumps(self.payload)
        return AIResult(raw, self.payload, "complete")


def extract_json(raw_text: str) -> str:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end >= start:
        return cleaned[start : end + 1]
    return cleaned


def normalize_json_text(raw_text: str) -> str:
    cleaned = extract_json(raw_text)
    return re.sub(r",\s*([}\]])", r"\1", cleaned)
