from __future__ import annotations

from pathlib import Path

from sonar.ai.evidence_briefs import EvidenceBriefGenerator
from sonar.ai.provider import FakeProvider
from sonar.db import Database, utc_now


def make_database(tmp_path: Path) -> Database:
    return Database(tmp_path / "brief-test.db")


def anomaly_row() -> dict:
    return {
        "id": 1,
        "source_feed": "topstories",
        "metric_name": "story_volume",
        "metric_value": 12.0,
        "baseline_value": 4.0,
        "z_score": 2.5,
        "triggered_by": "story_volume,engagement_score",
        "detected_at": utc_now(),
        "news_aligned": 1,
    }


def stories() -> list[dict]:
    return [
        {
            "story_id": "123",
            "source_feed": "topstories",
            "title": "Example AI infrastructure story",
            "score": 42,
            "num_comments": 7,
            "created_at": utc_now(),
            "permalink": "https://news.ycombinator.com/item?id=123",
        }
    ]


def insert_anomaly(database: Database, anomaly: dict) -> None:
    payload = dict(anomaly)
    payload["explanation_status"] = "pending"
    payload["metric_version"] = 2
    database.insert_anomaly(payload)


def test_evidence_brief_generator_stores_audit_and_evidence(tmp_path: Path) -> None:
    database = make_database(tmp_path)
    anomaly = anomaly_row()
    insert_anomaly(database, anomaly)
    provider = FakeProvider(
        {
            "headline_summary": "AI infrastructure attention spiked",
            "topic": "AI Infrastructure",
            "event_type": "engagement_spike",
            "sentiment_label": "neutral",
            "confidence": 0.81,
            "is_news_aligned": True,
            "evidence": [
                {
                    "source": "hacker_news",
                    "id": "123",
                    "title": "Example AI infrastructure story",
                    "url": "https://news.ycombinator.com/item?id=123",
                    "reason_used": "High engagement anomaly",
                }
            ],
            "bullet_insights": ["Story volume increased."],
            "summary": "HN attention increased around AI infrastructure.",
        }
    )
    generator = EvidenceBriefGenerator(database=database, provider=provider)

    brief = generator.generate(
        anomaly=anomaly,
        news_context={"article_count": 0, "top_headlines": []},
        stories=stories(),
    )

    assert brief is not None
    assert brief["confidence"] == 0.81
    with database.connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM documents").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM ai_runs").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM brief_evidence").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM explanations").fetchone()["count"] == 1


def test_evidence_brief_generator_compacts_verbose_model_output(tmp_path: Path) -> None:
    database = make_database(tmp_path)
    anomaly = anomaly_row()
    insert_anomaly(database, anomaly)
    provider = FakeProvider(
        {
            "headline_summary": "The current Hacker News landscape is showing a very large and unusually broad engagement spike across multiple newstories metrics",
            "topic": "newstories feed engagement anomaly with many moving parts",
            "event_type": "engagement_spike",
            "sentiment_label": "neutral",
            "confidence": 0.91,
            "is_news_aligned": False,
            "evidence": [],
            "bullet_insights": [
                "A significant increase in story volume, average score, average comments, and engagement score was detected across the newstories feed.",
                "Several high-engagement submissions probably contributed to the movement in the monitoring window.",
                "The signal should be reviewed because it may reflect a short-lived platform attention shift.",
                "This fourth point should be removed by normalization.",
            ],
            "summary": "This summary is intentionally too long and should be compressed by the shared brief normalizer so that product dashboards do not need to carry the burden of cleaning verbose model output before rendering compact monitoring cards for analysts.",
        }
    )
    generator = EvidenceBriefGenerator(database=database, provider=provider)

    brief = generator.generate(
        anomaly=anomaly,
        news_context={"article_count": 0, "top_headlines": []},
        stories=stories(),
    )

    assert brief is not None
    assert len(brief["headline_summary"].split()) <= 16
    assert len(brief["topic"].split()) <= 4
    assert len(brief["bullet_insights"]) == 3
    assert all(len(item.split()) <= 18 for item in brief["bullet_insights"])
    assert len(brief["summary"].split()) <= 45
    assert brief["evidence"]
    assert brief["confidence"] == 0.49


def test_evidence_brief_generator_records_malformed_json_failure(tmp_path: Path) -> None:
    database = make_database(tmp_path)
    anomaly = anomaly_row()
    insert_anomaly(database, anomaly)
    provider = FakeProvider("not json")
    generator = EvidenceBriefGenerator(database=database, provider=provider)

    brief = generator.generate(
        anomaly=anomaly,
        news_context={"article_count": 0, "top_headlines": []},
        stories=stories(),
    )

    assert brief is None
    with database.connect() as conn:
        run = conn.execute("SELECT status, error, raw_response FROM ai_runs").fetchone()
        assert run["status"] == "failed"
        assert run["error"] == "invalid_json"
        assert run["raw_response"] == "not json"
        assert conn.execute("SELECT COUNT(*) AS count FROM explanations").fetchone()["count"] == 0
