from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryExhausted(Exception):
    pass


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    retries: int = 3,
    base_delay: float = 1.0,
    retry_on: tuple[type[Exception], ...] = (Exception,),
) -> T:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except retry_on as e:
            last_error = e
            if attempt == retries:
                break
            delay = base_delay * (2**attempt)
            logger.info(
                "Retry %d/%d after %s: %.1fs backoff",
                attempt + 1,
                retries,
                type(e).__name__,
                delay,
            )
            time.sleep(delay)

    raise RetryExhausted(
        f"Failed after {retries} retries: {last_error}"
    ) from last_error
