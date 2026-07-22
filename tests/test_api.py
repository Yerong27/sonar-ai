from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy import text

from sonar.api.main import create_app
from sonar.db import Database, utc_now


def make_client(database: Database) -> tuple[TestClient, Database]:
    app = create_app(database=database)
    return TestClient(app), database


def seed_database(database: Database) -> None:
    now = utc_now()
    with database.connect() as conn:
        conn.execute(
            text(
                """
            INSERT INTO hn_story_snapshots (
                story_id, source_feed, title, author, score, num_comments,
                created_at, permalink, url, collected_at, monitor_gap_flag,
                gap_duration_minutes
            ) VALUES (
                :story_id, :source_feed, :title, :author, :score, :num_comments,
                :created_at, :permalink, :url, :collected_at, :monitor_gap_flag,
                :gap_duration_minutes
            )
                """
            ),
            {
                "story_id": "123",
                "source_feed": "topstories",
                "title": "Example AI story",
                "author": "casey",
                "score": 42,
                "num_comments": 7,
                "created_at": now,
                "permalink": "https://news.ycombinator.com/item?id=123",
                "url": "https://example.com/story",
                "collected_at": now,
                "monitor_gap_flag": 0,
                "gap_duration_minutes": None,
            },
        )
        anomaly_id = conn.execute(
            text(
                """
            INSERT INTO anomalies (
                source_feed, metric_name, metric_value, baseline_value, z_score,
                triggered_by, detected_at, news_aligned, explanation_status,
                metric_version
            ) VALUES (
                :source_feed, :metric_name, :metric_value, :baseline_value,
                :z_score, :triggered_by, :detected_at, :news_aligned,
                :explanation_status, :metric_version
            )
            RETURNING id
                """
            ),
            {
                "source_feed": "topstories",
                "metric_name": "story_volume",
                "metric_value": 12.0,
                "baseline_value": 4.0,
                "z_score": 2.4,
                "triggered_by": "story_volume,engagement_score",
                "detected_at": now,
                "news_aligned": 1,
                "explanation_status": "complete",
                "metric_version": 2,
            },
        ).scalar_one()
        conn.execute(
            text(
                """
            INSERT INTO news_matches (
                anomaly_id, article_count, top_headlines, checked_at
            ) VALUES (:anomaly_id, :article_count, :top_headlines, :checked_at)
                """
            ),
            {
                "anomaly_id": anomaly_id,
                "article_count": 1,
                "top_headlines": json.dumps(
                    [{"title": "External confirmation", "url": "https://example.com/news"}]
                ),
                "checked_at": now,
            },
        )
        conn.execute(
            text(
                """
            INSERT INTO explanations (
                anomaly_id, response_json, created_at
            ) VALUES (:anomaly_id, :response_json, :created_at)
                """
            ),
            {
                "anomaly_id": anomaly_id,
                "response_json": json.dumps(
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
                "created_at": now,
            },
        )
        conn.execute(
            text(
                """
            INSERT INTO monitoring_summaries (
                source_scope, response_json, story_count, created_at
            ) VALUES (:source_scope, :response_json, :story_count, :created_at)
                """
            ),
            {
                "source_scope": "all_feeds",
                "response_json": json.dumps({"headline_summary": "AI dominates current HN"}),
                "story_count": 1,
                "created_at": now,
            },
        )
        conn.execute(
            text(
                """
            INSERT INTO aggregated_metrics (
                source_feed, window_start, window_end, story_volume, avg_score,
                avg_comments, engagement_score, growth_rate, metric_version,
                collected_at
            ) VALUES (
                :source_feed, :window_start, :window_end, :story_volume,
                :avg_score, :avg_comments, :engagement_score, :growth_rate,
                :metric_version, :collected_at
            )
                """
            ),
            {
                "source_feed": "topstories",
                "window_start": now,
                "window_end": now,
                "story_volume": 12,
                "avg_score": 42.0,
                "avg_comments": 7.0,
                "engagement_score": 49.0,
                "growth_rate": 1.25,
                "metric_version": 2,
                "collected_at": now,
            },
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


def test_status_handles_empty_database(database: Database) -> None:
    client, _ = make_client(database)

    response = client.get("/api/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["counts"]["stories"] == 0
    assert body["counts"]["anomalies"] == 0
    assert body["counts"]["briefs"] == 0


def test_health_endpoints(database: Database) -> None:
    client, _ = make_client(database)

    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ready"}


def test_production_frontend_origin_is_allowed(database: Database) -> None:
    client, _ = make_client(database)

    response = client.options(
        "/api/status",
        headers={
            "Origin": "https://sonar-ai-radar.liyerongvv.chatgpt.site",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "https://sonar-ai-radar.liyerongvv.chatgpt.site"
    )


def test_read_endpoints_return_seeded_data(database: Database) -> None:
    client, database = make_client(database)
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


def test_brief_detail_and_missing_brief(database: Database) -> None:
    client, database = make_client(database)
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


def test_run_once_is_not_public(database: Database) -> None:
    client, _ = make_client(database)

    response = client.post("/api/run-once")

    assert response.status_code == 404
