from __future__ import annotations

from argparse import Namespace
from typing import Any

import pytest
from sqlalchemy import text

import sonar.worker as worker
from sonar.db import CollectorLockUnavailable, Database
from sonar.services.collection import CollectionCycleService


class FakeHackerNews:
    def fetch_latest_stories(self, collected_at: str) -> list[dict[str, Any]]:
        return [
            {
                "story_id": "retry-safe-story",
                "source_feed": "topstories",
                "title": "Retry-safe collector test",
                "author": "sonar-test",
                "score": 42,
                "num_comments": 7,
                "created_at": collected_at,
                "permalink": "https://news.ycombinator.com/item?id=retry-safe-story",
                "url": None,
                "collected_at": collected_at,
                "monitor_gap_flag": 0,
                "gap_duration_minutes": None,
            }
        ]


class DisabledGemini:
    enabled = False
    last_error = None


class UnusedNewsClient:
    def search(self, _query: str) -> dict[str, Any]:
        raise AssertionError("NewsAPI must not be called in pipeline retry tests")


class UnusedBriefGenerator:
    enabled = False

    def generate(self, **_kwargs: Any) -> None:
        raise AssertionError("Gemini must not be called in pipeline retry tests")


def service_for(database: Database) -> CollectionCycleService:
    return CollectionCycleService(
        database=database,
        hackernews=FakeHackerNews(),
        news=UnusedNewsClient(),
        gemini=DisabledGemini(),
        brief_generator=UnusedBriefGenerator(),
    )


def test_same_run_id_replays_saved_result_without_duplicate_writes(database: Database) -> None:
    service = service_for(database)

    first = service.run_once("same-run-id")
    replay = service.run_once("same-run-id")

    assert first.status == "succeeded"
    assert first.replayed is False
    assert replay.status == "succeeded"
    assert replay.replayed is True
    assert replay.collected_at == first.collected_at
    with database.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM pipeline_runs")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM hn_story_snapshots")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM aggregated_metrics")).scalar_one() == 2


def test_failed_partial_run_is_diagnostic_and_retry_is_idempotent(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = service_for(database)
    original_insert_metric = database.insert_aggregated_metric
    should_fail = True

    def fail_first_metric(metric_row: dict[str, Any]) -> bool:
        nonlocal should_fail
        if should_fail:
            should_fail = False
            raise RuntimeError("deliberate metric failure")
        return original_insert_metric(metric_row)

    monkeypatch.setattr(database, "insert_aggregated_metric", fail_first_metric)
    with pytest.raises(RuntimeError, match="deliberate metric failure"):
        service.run_once("failed-then-retried")

    failed = database.get_pipeline_run("failed-then-retried")
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["error_stage"] == "building_metrics"
    assert "deliberate metric failure" in failed["error_message"]

    retried = service.run_once("failed-then-retried")
    assert retried.status == "succeeded"
    assert retried.attempt_count == 2
    with database.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM pipeline_runs")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM hn_story_snapshots")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM aggregated_metrics")).scalar_one() == 2


def test_database_lock_rejects_overlapping_collector(database: Database) -> None:
    contender = Database(engine=database.engine)

    with database.collector_lock():
        with pytest.raises(CollectorLockUnavailable):
            with contender.collector_lock():
                pytest.fail("second collector unexpectedly acquired the advisory lock")


def test_lock_contention_leaves_a_failed_pipeline_record(database: Database) -> None:
    service = service_for(database)

    with database.collector_lock():
        with pytest.raises(CollectorLockUnavailable):
            service.run_once("overlapping-run")

    failed = database.get_pipeline_run("overlapping-run")
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["error_stage"] == "lock"


def test_run_id_resolution_prefers_explicit_then_cloud_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SONAR_RUN_ID", "environment-run")
    monkeypatch.setenv("CLOUD_RUN_EXECUTION", "cloud-execution")
    assert worker.resolve_run_id("cli-run") == "cli-run"
    assert worker.resolve_run_id(None) == "environment-run"

    monkeypatch.delenv("SONAR_RUN_ID")
    assert worker.resolve_run_id(None) == "cloud-execution"

    monkeypatch.delenv("CLOUD_RUN_EXECUTION")
    assert worker.resolve_run_id(None)


def test_once_worker_returns_nonzero_when_collection_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        worker,
        "parse_args",
        lambda: Namespace(once=True, interval=1, run_id="failed-job-run"),
    )
    monkeypatch.setattr(worker.signal, "signal", lambda *_args: None)

    def fail_collection(_run_id: str) -> None:
        raise RuntimeError("deliberate worker failure")

    monkeypatch.setattr(worker, "run_collection_cycle", fail_collection)
    assert worker.main() == 1
