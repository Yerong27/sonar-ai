from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import SSLError
from urllib3.util.retry import Retry

from sonar.config import settings
from sonar.utils.backoff import with_exponential_backoff

logger = logging.getLogger(__name__)


class HackerNewsIngestionClient:
    def __init__(self) -> None:
        self.base_url = settings.hn_base_url.rstrip("/")
        self.timeout = (6, 20)
        self._session = self._build_session()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=2,
            connect=2,
            read=2,
            status=2,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=12,
            pool_maxsize=24,
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({"User-Agent": "sonar-hn-monitor/1.0"})
        return session

    def _reset_session(self) -> None:
        try:
            self._session.close()
        finally:
            self._session = self._build_session()

    def _get_json(self, path: str) -> object:
        url = f"{self.base_url}/{path}.json"
        try:
            response = self._session.get(url, timeout=self.timeout)
        except SSLError:
            # Rebuild the connection pool when TLS state becomes stale/interrupted.
            logger.warning("SSL error when requesting %s; rebuilding session and retrying once", url)
            self._reset_session()
            response = self._session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    @with_exponential_backoff(exceptions=(requests.RequestException,))
    def fetch_latest_stories(self, collected_at: str | None = None) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        collected_at = collected_at or datetime.now(timezone.utc).isoformat()

        for endpoint in settings.hn_story_endpoints:
            story_ids = self._fetch_story_ids(endpoint.strip())[: settings.max_story_ids]
            for story_id in story_ids:
                item = self._fetch_item(story_id)
                if not item or item.get("type") != "story":
                    continue
                rows.append(self._serialize_story(item, endpoint.strip(), collected_at))

        return rows

    def _fetch_story_ids(self, endpoint: str) -> list[int]:
        payload = self._get_json(endpoint)
        if not isinstance(payload, list):
            return []
        return [int(story_id) for story_id in payload]

    def _fetch_item(self, item_id: int) -> dict[str, object]:
        payload = self._get_json(f"item/{item_id}")
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _serialize_story(item: dict[str, object], source_feed: str, collected_at: str) -> dict[str, object]:
        timestamp = int(item.get("time", 0))
        created_at = (
            datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
            if timestamp
            else collected_at
        )
        return {
            "story_id": str(item.get("id", "")),
            "source_feed": source_feed,
            "title": str(item.get("title", "")),
            "author": str(item.get("by", "unknown")),
            "score": int(item.get("score", 0)),
            "num_comments": int(item.get("descendants", 0)),
            "created_at": created_at,
            "url": str(item.get("url", "")),
            "permalink": f"https://news.ycombinator.com/item?id={item.get('id', '')}",
            "collected_at": collected_at,
        }
