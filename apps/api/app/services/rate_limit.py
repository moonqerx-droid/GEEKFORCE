from collections import defaultdict, deque
from datetime import timedelta

from app.core.security import utc_now


class RateLimitExceeded(Exception):
    pass


class InMemoryRateLimiter:
    def __init__(self):
        self._events: dict[tuple[str, str], deque] = defaultdict(deque)

    def check(self, bucket: str, key: str, limit: int, window: timedelta) -> None:
        """Count this attempt and refuse it once the limit is reached."""
        self.ensure_allowed(bucket, key, limit, window)
        self.record(bucket, key)

    def ensure_allowed(self, bucket: str, key: str, limit: int, window: timedelta) -> None:
        """Refuse without counting — for limits that only count failures."""
        now = utc_now()
        events = self._events[(bucket, key)]
        while events and now - events[0] >= window:
            events.popleft()
        if len(events) >= limit:
            raise RateLimitExceeded()

    def record(self, bucket: str, key: str) -> None:
        self._events[(bucket, key)].append(utc_now())
