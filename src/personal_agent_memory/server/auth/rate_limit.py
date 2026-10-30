"""Bounded, process-local sliding windows. Proxy trust is configured in the ASGI server."""

import time
from collections import OrderedDict, deque

from starlette.requests import Request


def client_ip(request: Request) -> str:
    # Never trust arbitrary Forwarded/X-Forwarded-For headers here.
    return request.client.host if request.client else 'unknown'


class RateLimiter:
    def __init__(self, limit: int, *, window: float = 60, max_keys: int = 10000) -> None:
        self.limit = limit
        self.window = window
        self.max_keys = max_keys
        self.attempts: OrderedDict[str, deque[float]] = OrderedDict()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        # Keys are ordered by last accepted attempt; expired keys cannot accumulate.
        while self.attempts and next(iter(self.attempts.values()))[-1] <= now - self.window:
            self.attempts.popitem(last=False)
        attempts = self.attempts.get(key)
        if attempts is None:
            if len(self.attempts) >= self.max_keys:
                return False
            attempts = deque()
            self.attempts[key] = attempts
        while attempts and attempts[0] <= now - self.window:
            attempts.popleft()
        if len(attempts) >= self.limit:
            return False
        attempts.append(now)
        self.attempts.move_to_end(key)
        return True
