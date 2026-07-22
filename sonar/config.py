from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def csv_env(name: str, default: str) -> list[str]:
    return [value.strip() for value in os.getenv(name, default).split(",") if value.strip()]


@dataclass(slots=True)
class Settings:
    newsapi_key: str = os.getenv("NEWSAPI_KEY", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    hn_story_endpoints: list[str] = field(
        default_factory=lambda: os.getenv(
            "SONAR_HN_ENDPOINTS",
            "topstories,newstories",
        ).split(",")
    )
    poll_interval_seconds: int = int(os.getenv("SONAR_POLL_INTERVAL_SECONDS", "300"))
    # Change 2: configurable gap threshold for monitoring reliability.
    monitor_gap_threshold_seconds: int = int(
        os.getenv("SONAR_MONITOR_GAP_THRESHOLD_SECONDS", "600")
    )
    alert_window_minutes: int = int(os.getenv("SONAR_ALERT_WINDOW_MINUTES", "30"))
    anomaly_window: int = int(os.getenv("SONAR_ANOMALY_WINDOW", "6"))
    anomaly_zscore_threshold: float = float(os.getenv("SONAR_ZSCORE_THRESHOLD", "2.0"))
    monitoring_interval_seconds: int = int(os.getenv("SONAR_MONITORING_INTERVAL_SECONDS", "1800"))
    monitoring_story_sample_size: int = int(os.getenv("SONAR_MONITORING_STORY_SAMPLE_SIZE", "8"))
    cors_origins: list[str] = field(
        default_factory=lambda: csv_env(
            "SONAR_CORS_ORIGINS",
            "https://sonar-ai-radar.liyerongvv.chatgpt.site,"
            "http://localhost:5173,http://127.0.0.1:5173,"
            "http://localhost:5174,http://127.0.0.1:5174",
        )
    )
    data_dir: Path = Path(__file__).resolve().parent / "data"
    database_url: str = field(default_factory=lambda: required_env("DATABASE_URL"))
    max_story_ids: int = int(os.getenv("SONAR_MAX_STORY_IDS", "60"))
    metric_semantics_version: int = 2
    newsapi_endpoint: str = "https://newsapi.org/v2/everything"
    hn_base_url: str = "https://hacker-news.firebaseio.com/v0"
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
