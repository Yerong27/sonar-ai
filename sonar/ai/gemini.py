from __future__ import annotations

import json
import logging
import re

import google.generativeai as genai
from google.api_core.exceptions import GoogleAPICallError, ResourceExhausted

from sonar.config import settings

logger = logging.getLogger(__name__)


class GeminiExplainer:
    def __init__(self) -> None:
        self.enabled = bool(settings.gemini_api_key)
        if self.enabled:
            genai.configure(api_key=settings.gemini_api_key)
            self.model = genai.GenerativeModel(settings.gemini_model)
        else:
            self.model = None
        self.last_error: str | None = None

    def explain(self, anomaly: dict, news_context: dict[str, object]) -> dict | None:
        if not self.enabled or not self.model:
            return None

        prompt = f"""
Return only valid JSON. No markdown, no explanation.
You are a monitoring system analyst. Explain this Hacker News anomaly.
Write like a professional incident brief — be specific and concise.

Required JSON schema:
{{
  "headline_summary": "One sentence: what happened and why it matters. Max 16 words. Write like a monitoring alert title, NOT an essay.",
  "keywords": ["string — max 6 keywords"],
  "topic": "string — concise 2–4 word topic label",
  "sentiment_label": "positive|negative|neutral|mixed",
  "confidence": 0.0,
  "is_news_aligned": true,
  "event_type": "string — e.g. engagement_spike, viral_breakout, controversy, product_launch",
  "triggered_by": ["string"],
  "bullet_insights": [
    "What changed: one sentence, max 18 words.",
    "Why it likely changed: one sentence, max 18 words.",
    "Why it matters: one sentence, max 18 words."
  ],
  "summary": "string — 2 short sentences, max 45 words total"
}}

Anomaly:
{json.dumps(anomaly)}

News context:
{json.dumps(news_context)}
"""
        return self._generate_json(prompt)

    def summarize_monitoring_snapshot(self, stories: list[dict]) -> dict | None:
        if not self.enabled or not self.model or not stories:
            return None

        prompt = f"""
Return only valid JSON. No markdown, no explanation.
You are a monitoring system analyst summarizing the current Hacker News landscape.

CRITICAL INSTRUCTIONS:
- headline_summary must read like a monitoring brief title (max 12 words). NOT an essay introduction.
- top_topics must contain no more than 5 concise themes that summarize the overall landscape.
- top_topics must be concise labels (2–4 words each, e.g. "AI Model Releases", "Cloud Pricing").
- Topics must describe the subject matter, never the feed mechanics, monitoring process, or engagement measurements.
- Return 8–15 keyword_signals when the supplied stories contain that many meaningful concepts; do not reduce the result to a few mutually exclusive clusters.
- A keyword_signal is a reusable, standalone concept: an entity, product, technology, protocol, research area, policy issue, or specific technical subject.
- Each concept must be a noun or noun phrase a reader could understand without seeing the source headline.
- Do not return grammatical connectors, verbs, adjectives, headline scaffolding, or fragments of a title.
- Do not return an umbrella label when a more concrete recurring concept is available.
- One concept may be supported by the same story as another concept; concepts are not mutually exclusive.
- Prefer concepts supported by at least 2 supplied stories. A single sampled story is allowed only when the concept is highly specific and aliases can find related stories in the wider database window.
- concept_type must be exactly one of: entity, product, technology, protocol, research_area, policy_issue, technical_subject.
- aliases must include only genuine alternative names, abbreviations, or spelling variants useful for matching additional titles.
- supporting_story_ids must identify supplied stories where the concept is central.
- confidence is the probability from 0 to 1 that the label is a meaningful standalone concept and central to its supporting stories.
- Never invent IDs or aliases.
- bullet_insights must each be a single sentence with a maximum of 18 words.
- dominant_theme must be 3–5 words.
- summary must be 2 short sentences with a maximum of 45 words total.
- Select a maximum of 5 notable_story_ids.
- sentiment_distribution values must sum to approximately 1.0.

Required JSON schema:
{{
  "headline_summary": "string — a concise monitoring brief headline, max 12 words",
  "keyword_signals": [
    {{
      "concept": "string — a concrete 1–5 word standalone concept",
      "concept_type": "entity | product | technology | protocol | research_area | policy_issue | technical_subject",
      "aliases": ["string — genuine matching aliases only"],
      "supporting_story_ids": ["string — exact supplied story IDs where central"],
      "confidence": 0.0
    }}
  ],
  "top_topics": ["string — max 5, each 2–4 words"],
  "dominant_theme": "string — the single most prominent theme in 3–5 words",
  "sentiment_distribution": {{
    "positive": 0.0,
    "negative": 0.0,
    "neutral": 0.0,
    "mixed": 0.0
  }},
  "notable_story_ids": ["string — max 5"],
  "bullet_insights": ["string — max 3 concise observations, each one sentence and max 18 words"],
  "summary": "string — 2 short sentences, max 45 words total"
}}

Recent stories:
{json.dumps(stories)}
"""
        return self._generate_json(prompt)

    def _generate_json(self, prompt: str) -> dict | None:
        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "max_output_tokens": 4096,
                },
            )
            raw_text = response.text.strip()
        except ResourceExhausted as exc:
            self.last_error = f"quota_exceeded: {exc}"
            logger.warning("Gemini quota unavailable: %s", exc)
            return None
        except GoogleAPICallError as exc:
            self.last_error = f"api_error: {exc}"
            logger.warning("Gemini API call failed: %s", exc)
            return None
        except Exception as exc:
            self.last_error = f"unexpected_error: {exc}"
            logger.warning("Gemini request failed unexpectedly: %s", exc)
            return None

        try:
            self.last_error = None
            cleaned_text = self._normalize_json_text(raw_text)
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            self.last_error = "invalid_json"
            logger.warning("Gemini returned non-JSON content: %s", raw_text)
            return None

    @staticmethod
    def _extract_json(raw_text: str) -> str:
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
            cleaned = cleaned[start : end + 1]
        return cleaned

    @classmethod
    def _normalize_json_text(cls, raw_text: str) -> str:
        cleaned = cls._extract_json(raw_text)
        # Gemini sometimes returns JSON-like output with trailing commas.
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
        return cleaned
