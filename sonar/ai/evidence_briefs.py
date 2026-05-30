from __future__ import annotations

import json
import re
from typing import Any

from sonar.ai.brief_schema import normalize_brief_payload
from sonar.ai.provider import AIProvider, GeminiProvider
from sonar.db import Database, db

BRIEF_SCHEMA_NAME = "sonar_evidence_brief_v1"


class EvidenceBriefGenerator:
    def __init__(
        self,
        *,
        database: Database | None = None,
        provider: AIProvider | None = None,
    ) -> None:
        self.database = database or db
        self.provider = provider or GeminiProvider()

    @property
    def enabled(self) -> bool:
        return bool(self.provider.enabled)

    def generate(
        self,
        *,
        anomaly: dict[str, Any],
        news_context: dict[str, Any],
        stories: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        evidence = self._build_evidence(anomaly=anomaly, news_context=news_context, stories=stories)
        prompt = self._build_prompt(anomaly=anomaly, news_context=news_context, evidence=evidence)

        result = self.provider.generate_json(prompt, BRIEF_SCHEMA_NAME)
        ai_run_id = self.database.insert_ai_run(
            anomaly_id=int(anomaly["id"]),
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            schema_name=BRIEF_SCHEMA_NAME,
            prompt=prompt,
            raw_response=result.raw_response,
            parsed_json=result.parsed_json,
            status=result.status,
            error=result.error,
        )

        for rank, item in enumerate(evidence, start=1):
            self.database.insert_brief_evidence(
                ai_run_id=ai_run_id,
                document_id=int(item["document_id"]),
                reason_used=str(item["reason_used"]),
                rank=rank,
            )

        if result.status != "complete" or result.parsed_json is None:
            return None

        brief = self._normalize_brief(result.parsed_json, evidence)
        # Store normalized brief in ai_runs-compatible legacy explanations table.
        self.database.insert_explanation(int(anomaly["id"]), brief)
        return brief

    def _build_evidence(
        self,
        *,
        anomaly: dict[str, Any],
        news_context: dict[str, Any],
        stories: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        keywords = self._keywords(anomaly)
        ranked_stories = sorted(
            stories,
            key=lambda story: (
                story.get("source_feed") == anomaly.get("source_feed"),
                int(story.get("score", 0) or 0) + int(story.get("num_comments", 0) or 0),
            ),
            reverse=True,
        )

        evidence: list[dict[str, Any]] = []
        for story in ranked_stories[:5]:
            source_id = str(story.get("story_id") or story.get("id") or story.get("title"))
            title = str(story.get("title") or "Untitled Hacker News story")
            content = " ".join(
                [
                    title,
                    f"feed={story.get('source_feed')}",
                    f"score={story.get('score')}",
                    f"comments={story.get('num_comments')}",
                ]
            )
            document_id = self.database.upsert_document(
                source="hacker_news",
                source_id=source_id,
                title=title,
                url=story.get("permalink") or story.get("url"),
                content=content,
                metadata={
                    "source_feed": story.get("source_feed"),
                    "score": story.get("score"),
                    "num_comments": story.get("num_comments"),
                    "created_at": story.get("created_at"),
                },
            )
            evidence.append(
                {
                    "document_id": document_id,
                    "source": "hacker_news",
                    "id": source_id,
                    "title": title,
                    "url": story.get("permalink") or story.get("url"),
                    "reason_used": "Recent high-engagement story near the anomaly window.",
                    "content": content,
                }
            )

        for index, headline in enumerate(news_context.get("top_headlines") or [], start=1):
            title, url = self._headline_title_url(headline)
            if not title:
                continue
            source_id = f"{anomaly.get('id')}-news-{index}"
            document_id = self.database.upsert_document(
                source="newsapi",
                source_id=source_id,
                title=title,
                url=url,
                content=title,
                metadata={"keywords": keywords, "anomaly_id": anomaly.get("id")},
            )
            evidence.append(
                {
                    "document_id": document_id,
                    "source": "newsapi",
                    "id": source_id,
                    "title": title,
                    "url": url,
                    "reason_used": "External news context returned for the anomaly query.",
                    "content": title,
                }
            )

        return evidence[:8]

    @staticmethod
    def _headline_title_url(headline: Any) -> tuple[str, str | None]:
        if isinstance(headline, dict):
            return str(headline.get("title") or ""), headline.get("url")
        return str(headline or ""), None

    @staticmethod
    def _keywords(anomaly: dict[str, Any]) -> list[str]:
        raw = " ".join(
            [
                str(anomaly.get("source_feed") or ""),
                str(anomaly.get("metric_name") or ""),
                str(anomaly.get("triggered_by") or ""),
            ]
        )
        return [part for part in re.split(r"[\W_]+", raw.lower()) if len(part) > 2]

    @staticmethod
    def _build_prompt(
        *,
        anomaly: dict[str, Any],
        news_context: dict[str, Any],
        evidence: list[dict[str, Any]],
    ) -> str:
        evidence_payload = [
            {
                "source": item["source"],
                "id": item["id"],
                "title": item["title"],
                "url": item.get("url"),
                "reason_used": item["reason_used"],
                "content": item["content"],
            }
            for item in evidence
        ]
        return f"""
Return only valid JSON. No markdown, no explanation.
You are Sonar's monitoring analyst. Generate an evidence-grounded incident brief.

Rules:
- Use only the evidence listed below.
- If evidence is weak, set confidence below 0.5.
- Do not invent company names, causes, dates, or external events.
- Include at least one evidence item if evidence is provided.
- headline_summary must be a monitoring alert title, max 16 words.
- topic must be a concise 2-4 word label.
- bullet_insights must contain at most 3 items.
- Each bullet_insight must be one sentence and max 18 words.
- summary must be 2 short sentences and max 45 words total.

Required JSON schema:
{{
  "headline_summary": "string — max 16 words",
  "topic": "string — 2-4 words",
  "event_type": "engagement_spike | controversy | product_launch | security_incident | research_breakthrough | other",
  "sentiment_label": "positive | negative | neutral | mixed",
  "confidence": 0.0,
  "is_news_aligned": true,
  "evidence": [
    {{
      "source": "hacker_news | newsapi | historical_brief",
      "id": "string",
      "title": "string",
      "url": "string",
      "reason_used": "string"
    }}
  ],
  "bullet_insights": ["string — max 3, each max 18 words"],
  "summary": "string — 2 short sentences, max 45 words total"
}}

Anomaly:
{json.dumps(anomaly)}

News context:
{json.dumps(news_context)}

Evidence:
{json.dumps(evidence_payload)}
"""

    @staticmethod
    def _normalize_brief(
        payload: dict[str, Any],
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return normalize_brief_payload(payload, fallback_evidence=evidence)
