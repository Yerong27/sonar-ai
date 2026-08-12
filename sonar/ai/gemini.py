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

    def _review_topic_clusters(self, stories: list[dict], summary: dict) -> dict:
        if not summary or not isinstance(summary.get("topic_signals"), list):
            return summary

        candidates = summary.get("topic_signals") or []
        if not candidates:
            return summary

        validation_prompt = f"""
Return only valid JSON. No markdown, no explanation.
You are the independent quality reviewer for proposed Hacker News topic clusters.

Reject a cluster unless every included story shares one concrete, discriminating subject.
A broad professional domain is not a topic. For example, unrelated language releases,
compiler implementations, and coding practices do not become one trend merely because
they are all software engineering. Likewise, chip-company business news, local inference,
and data-center finance do not become one trend merely because they involve hardware.

REVIEW RULES:
- Judge the supplied titles independently; do not trust the proposed confidence.
- Keep only clusters with at least 3 stories after review.
- The final 2–5 word label must accurately predict what every supporting story discusses.
- Reject clusters connected only by a broad industry, profession, or generic technology category.
- Remove an individual story when it is only tangentially related.
- A story may appear in at most one accepted cluster.
- When two clusters overlap, retain only the narrower, more coherent cluster.
- You may rename a retained cluster, but may not add stories or invent a new cluster.
- confidence must be conservative. Use 1.0 only for near-duplicate coverage of the same event.
- Return an empty accepted_topics list when no proposal meets the standard.

Required JSON schema:
{{
  "accepted_topics": [
    {{
      "concept": "string — specific 2–5 word topic",
      "aliases": ["string — specific 2–5 word equivalent phrases"],
      "supporting_story_ids": ["string — at least 3 exact IDs retained from one proposal"],
      "confidence": 0.0
    }}
  ]
}}

Stories:
{json.dumps([{"story_id": story.get("story_id"), "title": story.get("title")} for story in stories])}

Proposed clusters:
{json.dumps(candidates)}
"""
        validated = self._generate_json(validation_prompt)
        accepted = validated.get("accepted_topics") if isinstance(validated, dict) else None
        summary["topic_signals"] = accepted if isinstance(accepted, list) else []
        summary["top_topics"] = [
            str(item.get("concept"))
            for item in summary["topic_signals"][:5]
            if isinstance(item, dict) and item.get("concept")
        ]
        if summary["top_topics"]:
            summary["dominant_theme"] = summary["top_topics"][0]
        return summary

    def summarize_monitoring_snapshot(self, stories: list[dict]) -> dict | None:
        if not self.enabled or not self.model or not stories:
            return None

        prompt = f"""
Return only valid JSON. No markdown, no explanation.
You are a monitoring system analyst summarizing the current Hacker News landscape.

CRITICAL INSTRUCTIONS:
- headline_summary must read like a monitoring brief title (max 12 words). NOT an essay introduction.
- First cluster the supplied stories by a concrete shared subject. Name a topic only after its supporting stories have been selected.
- top_topics must be drawn from the validated topic_signals and contain no more than 5 concise labels.
- top_topics must be concise labels (2–4 words each, e.g. "AI Model Releases", "Cloud Pricing").
- Topics must describe the subject matter, never the feed mechanics, monitoring process, or engagement measurements.
- Return between 3 and 8 topic_signals only when the supplied stories justify that many. Return fewer, or an empty list, rather than forcing unrelated stories together.
- Each topic_signal must contain at least 3 supplied stories whose central subject is genuinely the same.
- Assign a story to at most one topic_signal. Put stories that do not belong to a coherent recurring topic in unclustered_story_ids.
- Do not create a topic merely to cover every story or to reach a target count.
- A topic signal is a cross-story theme such as "AI Agent Infrastructure", "Technology Regulation", or "Privacy and Identity". It is not limited to a repeated company or product name.
- Each topic label must be a specific 2–5 word noun phrase that explains what the supporting stories are collectively about.
- Do not return grammatical connectors, actions, qualities, title fragments, generic words such as "Technology", or a single named entity unless multiple stories genuinely discuss it as a shared subject.
- aliases may include only specific 2–5 word alternative phrases that describe the same subject and are useful for matching additional story titles.
- supporting_story_ids must contain at least 3 exact supplied IDs whose stories substantively belong to the topic.
- confidence is the probability from 0 to 1 that every supporting story belongs to the same coherent subject; use a conservative value.
- Topic evidence sets must be distinct. Do not return broad and narrow versions of the same cluster.
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
      "supporting_story_ids": ["string — at least 3 exact supplied story IDs in this topic"],
      "confidence": 0.0
    }}
  ],
  "unclustered_story_ids": ["string — exact supplied IDs not assigned to a coherent recurring topic"],
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
        summary = self._generate_json(prompt)
        if not summary:
            return summary
        return self._review_topic_clusters(stories, summary)

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
