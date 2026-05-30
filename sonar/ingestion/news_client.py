from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from sonar.config import settings

logger = logging.getLogger(__name__)


class NewsValidationClient:
    def __init__(self) -> None:
        self.enabled = bool(settings.newsapi_key)
        self._session = self._build_session()

    @staticmethod
    def _build_session() -> requests.Session:
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
        adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=8)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({"User-Agent": "sonar-news-validator/1.0"})
        return session

    def search(self, query: str) -> dict[str, object]:
        if not self.enabled:
            return {"article_count": 0, "top_headlines": []}

        params = {
            "q": query,
            "apiKey": settings.newsapi_key,
            "language": "en",
            "sortBy": "publishedAt",
            "from": (datetime.now(timezone.utc) - timedelta(days=2)).date().isoformat(),
            "pageSize": 5,
        }
        try:
            response = self._session.get(settings.newsapi_endpoint, params=params, timeout=(6, 12))
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            logger.warning("NewsAPI request failed for query %r: %s", query, exc)
            return {"article_count": 0, "top_headlines": []}

        articles = payload.get("articles", [])
        return {
            "article_count": len(articles),
            "top_headlines": [article.get("title", "") for article in articles[:3]],
        }
