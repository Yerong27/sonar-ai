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
- top_topics must be 3–5 stable conceptual themes supported by multiple supplied stories.
- top_topics must be concise labels (2–4 words each, e.g. "AI Model Releases", "Cloud Pricing").
- Topics must describe the subject matter, never the feed mechanics, monitoring process, or engagement measurements.
- Build 8–12 topic_signals by grouping related stories into meaningful recurring subject areas.
- A topic signal is a cross-story theme such as "AI Agent Infrastructure", "Technology Regulation", or "Privacy and Identity". It is not limited to a repeated company or product name.
- Each topic label must be a specific 2–5 word noun phrase that explains what the supporting stories are collectively about.
- Do not return grammatical connectors, actions, qualities, title fragments, generic words such as "Technology", or a single named entity unless multiple stories genuinely discuss it as a shared subject.
- aliases may include only genuine alternative names, abbreviations, or closely related matching phrases useful for finding more stories in the same topic.
- supporting_story_ids must contain 2–6 exact supplied IDs whose stories substantively belong to the topic, even when their titles use different wording.
- Omit single-story topics. Cover the breadth of the supplied landscape instead of collapsing everything into a few dominant brands.
- Prefer clusters with 3 or more supporting stories, but retain useful 2-story clusters when they represent a distinct recurring subject.
- Prefer distinct topics with different evidence sets; do not return broad and narrow versions of the same cluster.
- Never invent IDs or aliases.
- bullet_insights must each be a single sentence with a maximum of 18 words.
- dominant_theme must be 3–5 words.
- summary must be 2 short sentences with a maximum of 45 words total.
- Select a maximum of 5 notable_story_ids.
- sentiment_distribution values must sum to approximately 1.0.

Required JSON schema:
{{
  "headline_summary": "string — a concise monitoring brief headline, max 12 words",
  "topic_signals": [
    {{
      "concept": "string — a specific 2–5 word cross-story topic",
      "aliases": ["string — genuine topic matching phrases only"],
      "supporting_story_ids": ["string — 2–6 exact supplied story IDs in this topic"]
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
            response = self.model.generate_content(prompt)
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
