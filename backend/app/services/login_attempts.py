import json
from math import ceil
from time import time

from limits.storage import MemoryStorage

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60


class LoginAttempts:
    def __init__(self) -> None:
        self._storage = MemoryStorage()

    def retry_after(self, email: str, ip: str) -> int | None:
        key = self._key(email, ip)
        if self._storage.get(f"locked:{key}"):
            return max(1, ceil(self._storage.get_expiry(f"locked:{key}") - time()))
        return None

    def record_failure(self, email: str, ip: str) -> int | None:
        remaining = self.retry_after(email, ip)
        if remaining is not None:
            return remaining
        key = self._key(email, ip)
        if self._storage.incr(key, LOCKOUT_SECONDS) >= MAX_ATTEMPTS:
            self._storage.incr(f"locked:{key}", LOCKOUT_SECONDS)
            self._storage.clear(key)
            return LOCKOUT_SECONDS
        return None

    def reset(self, email: str, ip: str) -> None:
        self._storage.clear(self._key(email, ip))

    @staticmethod
    def _key(email: str, ip: str) -> str:
        return json.dumps([email, ip])
