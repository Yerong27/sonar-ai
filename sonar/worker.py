from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from uuid import uuid4

from sonar.config import settings
from sonar.services.collection import run_collection_cycle

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Sonar background collection worker.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one collection cycle and exit.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=settings.poll_interval_seconds,
        help="Seconds between scheduled collection cycles.",
    )
    parser.add_argument(
        "--run-id",
        help="Stable logical run ID. Reuse this value when retrying the same run.",
    )
    return parser.parse_args()


def resolve_run_id(explicit_run_id: str | None) -> str:
    return (
        (explicit_run_id or "").strip()
        or os.getenv("SONAR_RUN_ID", "").strip()
        or os.getenv("CLOUD_RUN_EXECUTION", "").strip()
        or str(uuid4())
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = parse_args()
    should_stop = False

    def handle_stop(signum: int, _frame: object) -> None:
        nonlocal should_stop
        should_stop = True
        logger.info("Received signal %s; stopping after current wait/cycle", signum)

    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)

    while not should_stop:
        try:
            run_id = resolve_run_id(args.run_id if args.once else None)
            result = run_collection_cycle(run_id)
            logger.info(
                "Collection cycle completed: %s",
                json.dumps(result.to_dict(), sort_keys=True),
            )
        except Exception:
            logger.exception(
                "Collection cycle failed for run_id=%s",
                locals().get("run_id", "unknown"),
            )
            if args.once:
                return 1

        if args.once:
            return 0

        slept = 0
        while slept < args.interval and not should_stop:
            time.sleep(min(1, args.interval - slept))
            slept += 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
