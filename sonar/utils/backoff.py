from __future__ import annotations

import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)


def with_exponential_backoff(
    retries: int = 4,
    base_delay: float = 1.5,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = base_delay
            for attempt in range(1, retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    if attempt == retries:
                        raise
                    logger.warning(
                        "Retrying %s after error on attempt %s/%s: %s",
                        func.__name__,
                        attempt,
                        retries,
                        exc,
                    )
                    time.sleep(delay)
                    delay *= 2
            return None

        return wrapper

    return decorator
