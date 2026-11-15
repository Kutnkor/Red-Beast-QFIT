"""Small in-memory TTL cache for archive metadata."""
from __future__ import annotations

import time
from typing import Any, Hashable


class TTLCache:
    def __init__(self, ttl_seconds: float, max_entries: int = 512):
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self._data: dict[Hashable, tuple[float, Any]] = {}

    def get(self, key: Hashable) -> Any | None:
        hit = self._data.get(key)
        if hit is None:
            return None
        expires, value = hit
        if expires < time.monotonic():
            self._data.pop(key, None)
            return None
        return value

    def set(self, key: Hashable, value: Any) -> None:
        if self.ttl <= 0:
            return
        if len(self._data) >= self.max_entries:
            oldest = min(self._data, key=lambda k: self._data[k][0])
            self._data.pop(oldest, None)
        self._data[key] = (time.monotonic() + self.ttl, value)

    def clear(self) -> None:
        self._data.clear()
