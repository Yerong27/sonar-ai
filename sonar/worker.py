from __future__ import annotations

import argparse
import logging
import signal
import sys
import time

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
    return parser.parse_args()


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
            result = run_collection_cycle()
            logger.info("Collection cycle completed: %s", result.to_dict())
        except Exception:
            logger.exception("Collection cycle failed")
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
