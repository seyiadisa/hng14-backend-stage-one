import asyncio
import copy
from collections import OrderedDict
from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable


@dataclass
class CacheEntry:
    value: Any
    expires_at: float


class TTLQueryCache:
    def __init__(
        self,
        ttl_seconds: int = 60,
        max_entries: int = 512,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._clock = clock
        self._items: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._items.get(key)
            if entry is None:
                return None

            if entry.expires_at <= self._clock():
                self._items.pop(key, None)
                return None

            self._items.move_to_end(key)
            return copy.deepcopy(entry.value)

    async def set(self, key: str, value: Any) -> None:
        async with self._lock:
            self._items[key] = CacheEntry(
                value=copy.deepcopy(value),
                expires_at=self._clock() + self.ttl_seconds,
            )
            self._items.move_to_end(key)

            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)

    async def clear(self) -> None:
        async with self._lock:
            self._items.clear()


profile_query_cache = TTLQueryCache()


async def invalidate_profile_query_cache() -> None:
    # CSV ingestion should call this after each committed chunk in the next slice.
    await profile_query_cache.clear()
