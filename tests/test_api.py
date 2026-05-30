from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from sonar.api.main import create_app
from sonar.db import Database, utc_now


class FakeCollector:
    def run_once(self) -> None:
        return None


def make_client(tmp_path: Path) -> tuple[TestClient, Database]:
    database = Database(tmp_path / "sonar-test.db")
    app = create_app(database=database, collector_factory=FakeCollector)
    return TestClient(app), database


def seed_database(database: Database) -> None:
    now = utc_now()
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO hn_story_snapshots (
                story_id, source_feed, title, author, score, num_comments,
                created_at, permalink, url, collected_at, monitor_gap_flag,
                gap_duration_minutes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "123",
                "topstories",
                "Example AI story",
                "casey",
                42,
                7,
                now,
                "https://news.ycombinator.com/item?id=123",
                "https://example.com/story",
                now,
                0,
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO anomalies (
                source_feed, metric_name, metric_value, baseline_value, z_score,
                triggered_by, detected_at, news_aligned, explanation_status,
                metric_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "topstories",
                "story_volume",
                12.0,
                4.0,
                2.4,
                "story_volume,engagement_score",
                now,
                1,
                "complete",
                2,
            ),
        )
        anomaly_id = conn.execute("SELECT id FROM anomalies LIMIT 1").fetchone()["id"]
        conn.execute(
            """
            INSERT INTO news_matches (
                anomaly_id, article_count, top_headlines, checked_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                anomaly_id,
                1,
                json.dumps([{"title": "External confirmation", "url": "https://example.com/news"}]),
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO explanations (
                anomaly_id, response_json, created_at
            ) VALUES (?, ?, ?)
            """,
            (
                anomaly_id,
                json.dumps(
                    {
                        "headline_summary": "AI infrastructure story volume spiked",
                        "topic": "AI Infrastructure",
                        "sentiment_label": "neutral",
                        "confidence": 0.72,
                        "event_type": "engagement_spike",
                        "evidence": [
                            {
                                "source": "hacker_news",
                                "id": "123",
                                "title": "Example AI story",
                                "url": "https://news.ycombinator.com/item?id=123",
                                "reason_used": "High engagement anomaly",
                            }
                        ],
                        "bullet_insights": ["Story volume increased."],
                        "summary": "AI infrastructure attention increased in the current monitoring window.",
                    }
                ),
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO monitoring_summaries (
                source_scope, response_json, story_count, created_at
            ) VALUES (?, ?, ?, ?)
            """,
            ("all_feeds", json.dumps({"headline_summary": "AI dominates current HN"}), 1, now),
        )
        conn.execute(
            """
            INSERT INTO aggregated_metrics (
                source_feed, window_start, window_end, story_volume, avg_score,
                avg_comments, engagement_score, growth_rate, metric_version,
                collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("topstories", now, now, 12, 42.0, 7.0, 49.0, 1.25, 2, now),
        )
    document_id = database.upsert_document(
        source="hacker_news",
        source_id="123",
        title="Example AI story",
        url="https://news.ycombinator.com/item?id=123",
        content="Example AI story feed=topstories score=42 comments=7",
        metadata={"source_feed": "topstories"},
    )
    ai_run_id = database.insert_ai_run(
        anomaly_id=anomaly_id,
        provider="fake",
        model="fake-json",
        schema_name="sonar_evidence_brief_v1",
        prompt="prompt",
        raw_response='{"headline_summary":"AI infrastructure story volume spiked"}',
        parsed_json={"headline_summary": "AI infrastructure story volume spiked"},
        status="complete",
    )
    database.insert_brief_evidence(
        ai_run_id=ai_run_id,
        document_id=document_id,
        reason_used="High engagement anomaly",
        rank=1,
    )
    database.upsert_status("gemini_status", "ok")
    database.set_last_collection_time(now)


def test_status_handles_empty_database(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)

    response = client.get("/api/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["counts"]["stories"] == 0
    assert body["counts"]["anomalies"] == 0
    assert body["counts"]["briefs"] == 0


def test_read_endpoints_return_seeded_data(tmp_path: Path) -> None:
    client, database = make_client(tmp_path)
    seed_database(database)

    status = client.get("/api/status").json()
    assert status["counts"]["stories"] == 1
    assert status["counts"]["anomalies"] == 1
    assert status["counts"]["briefs"] == 1
    assert status["counts"]["ai_runs"] == 1
    assert status["counts"]["documents"] == 1
    assert status["gemini"]["value"] == "ok"

    stories = client.get("/api/stories?feed=topstories&limit=10").json()["stories"]
    assert stories[0]["title"] == "Example AI story"
    assert stories[0]["source_feed"] == "topstories"

    anomalies = client.get("/api/anomalies?news_aligned=true").json()["anomalies"]
    assert anomalies[0]["metric_name"] == "story_volume"
    assert anomalies[0]["explanation_status"] == "complete"

    briefs = client.get("/api/briefs").json()["briefs"]
    assert briefs[0]["headline_summary"] == "AI infrastructure story volume spiked"
    assert briefs[0]["evidence_count"] == 1
    assert briefs[0]["ai_run_id"] is not None
    assert briefs[0]["provider"] == "fake"

    timeline = client.get("/api/metrics/timeline").json()["timeline"]
    assert timeline[0]["source_feed"] == "topstories"
    assert timeline[0]["story_volume"] == 12

    overview = client.get("/api/dashboard/overview").json()
    assert overview["status"]["counts"]["stories"] == 1
    assert overview["top_stories"][0]["title"] == "Example AI story"
    assert overview["feed_summary"][0]["source_feed"] == "topstories"
    assert overview["latest_brief"]["headline_summary"] == "AI infrastructure story volume spiked"

    intelligence = client.get("/api/ai/intelligence").json()
    assert intelligence["latest_brief"]["headline_summary"] == "AI infrastructure story volume spiked"
    assert intelligence["ranked_themes"][0]["theme"] == "AI Infrastructure"
    assert intelligence["sentiment_distribution"][2]["label"] == "neutral"
    assert intelligence["keyword_bubbles"]
    assert intelligence["notable_stories"][0]["title"] == "Example AI story"


def test_brief_detail_and_missing_brief(tmp_path: Path) -> None:
    client, database = make_client(tmp_path)
    seed_database(database)

    brief_id = client.get("/api/briefs").json()["briefs"][0]["id"]
    detail = client.get(f"/api/briefs/{brief_id}")
    assert detail.status_code == 200
    assert detail.json()["brief"]["response"]["topic"] == "AI Infrastructure"
    assert detail.json()["ai_run"]["status"] == "complete"
    assert detail.json()["evidence"][0]["source"] == "hacker_news"
    assert detail.json()["news_matches"][0]["article_count"] == 1

    missing = client.get("/api/briefs/9999")
    assert missing.status_code == 404


def test_run_once_uses_injected_collector(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)

    response = client.post("/api/run-once")

    assert response.status_code == 200
    assert response.json() == {"status": "completed", "cycle": None}
