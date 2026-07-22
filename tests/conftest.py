from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "").strip()
if not TEST_DATABASE_URL:
    raise pytest.UsageError("TEST_DATABASE_URL must be set for PostgreSQL tests")

test_url = make_url(TEST_DATABASE_URL)
if test_url.database != "sonar_test":
    raise pytest.UsageError(
        "Refusing to run tests unless TEST_DATABASE_URL points to the sonar_test database"
    )

# Test modules import the application at collection time. Point its lazy global
# engine at the dedicated test database before those imports occur.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

TABLES = (
    "brief_evidence",
    "explanations",
    "ai_runs",
    "document_terms",
    "documents",
    "news_matches",
    "anomalies",
    "aggregated_metrics",
    "monitoring_summaries",
    "hn_story_snapshots",
    "system_status",
)


def _expected_alembic_heads() -> set[str]:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    return set(ScriptDirectory.from_config(config).get_heads())


def _truncate_database(engine: Engine) -> None:
    table_names = ", ".join(TABLES)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    if not inspect(engine).has_table("alembic_version"):
        engine.dispose()
        raise pytest.UsageError(
            "sonar_test has no Alembic schema; run DATABASE_URL=$TEST_DATABASE_URL "
            "alembic upgrade head first"
        )

    with engine.connect() as connection:
        current_heads = set(
            connection.execute(text("SELECT version_num FROM alembic_version")).scalars()
        )
    expected_heads = _expected_alembic_heads()
    if current_heads != expected_heads:
        engine.dispose()
        raise pytest.UsageError(
            f"sonar_test Alembic revision mismatch: current={sorted(current_heads)}, "
            f"expected={sorted(expected_heads)}"
        )

    yield engine
    engine.dispose()


@pytest.fixture
def database(test_engine: Engine):
    from sonar.db import Database

    _truncate_database(test_engine)
    database = Database(engine=test_engine)
    yield database
    _truncate_database(test_engine)
