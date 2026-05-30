from __future__ import annotations

import logging
import threading

from sonar.config import settings
from sonar.db import db
from sonar.services.collection import CollectionCycleResult, CollectionCycleService

logger = logging.getLogger(__name__)


class SonarCollector:
    def __init__(self) -> None:
        self.collection_service = CollectionCycleService()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def run_once(self) -> CollectionCycleResult:
        return self.collection_service.run_once()

    def reset_session_data(self) -> None:
        db.reset_monitoring_session()
        logger.info("Reset Sonar monitoring session data")

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as exc:
                logger.exception("Collector cycle failed: %s", exc)
            self._stop_event.wait(settings.poll_interval_seconds)
