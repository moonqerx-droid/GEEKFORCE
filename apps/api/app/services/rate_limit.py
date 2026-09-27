from collections import defaultdict, deque
from datetime import timedelta

from app.core.security import utc_now


class RateLimitExceeded(Exception):
    pass


class InMemoryRateLimiter:
    def __init__(self):
        self._events: dict[tuple[str, str], deque] = defaultdict(deque)

    def check(self, bucket: str, key: str, limit: int, window: timedelta) -> None:
        now = utc_now()
        events = self._events[(bucket, key)]
        while events and now - events[0] >= window:
            events.popleft()
        if len(events) >= limit:
            raise RateLimitExceeded()
        events.append(now)
