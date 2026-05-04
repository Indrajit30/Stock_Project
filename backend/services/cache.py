import asyncio
import logging
import time
from collections import defaultdict
from typing import Any, Callable

import orjson
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class CacheTTL:
    INTRADAY_PRICES = 300        # 5 minutes
    NEWS = 900                   # 15 minutes
    SENTIMENT = 1800             # 30 minutes
    FINANCIALS = 21600           # 6 hours
    EARNINGS_TRANSCRIPT = 86400  # 24 hours
    SEC_FILINGS = 2592000        # 30 days (permanent-ish)
    FILING_DIFFS = 2592000       # 30 days
    INSIDER_TRADES = 3600        # 1 hour
    PRECOMPUTED_REPORT = 43200   # 12 hours
    PEER_LIST = 86400            # 24 hours


class CacheManager:
    def __init__(self, redis_url: str | None = None):
        import os
        self._url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis: aioredis.Redis | None = None
        self._memory: dict[str, tuple[bytes, float | None]] = {}
        self._using_memory = False
        self._hits: dict[str, int] = defaultdict(int)
        self._misses: dict[str, int] = defaultdict(int)

    async def connect(self):
        try:
            self.redis = aioredis.from_url(self._url, decode_responses=False)
            await self.redis.ping()
            self._using_memory = False
            logger.info("connected to redis cache")
        except Exception as exc:
            logger.warning("redis unavailable, using in-memory cache: %s", exc)
            self.redis = None
            self._using_memory = True

    async def close(self):
        if self.redis:
            await self.redis.aclose()

    async def get(self, key: str) -> Any | None:
        if self._using_memory:
            item = self._memory.get(key)
            if item is None:
                self._misses[key.split(":")[0]] += 1
                return None
            raw, expires_at = item
            if expires_at is not None and expires_at < time.time():
                self._memory.pop(key, None)
                self._misses[key.split(":")[0]] += 1
                return None
        else:
            raw = await self.redis.get(key)
        prefix = key.split(":")[0]
        if raw is None:
            self._misses[prefix] += 1
            logger.debug("cache miss  key=%s", key)
            return None
        self._hits[prefix] += 1
        logger.debug("cache hit   key=%s", key)
        return orjson.loads(raw)

    async def set(self, key: str, value: Any, ttl_seconds: int):
        raw = orjson.dumps(value)
        if self._using_memory:
            expires_at = time.time() + ttl_seconds if ttl_seconds else None
            self._memory[key] = (raw, expires_at)
            return
        await self.redis.set(key, raw, ex=ttl_seconds)

    async def get_or_fetch(
        self, key: str, fetch_fn: Callable, ttl_seconds: int
    ) -> Any:
        cached = await self.get(key)
        if cached is not None:
            return cached

        lock_key = f"lock:{key}"
        if self._using_memory:
            result = await fetch_fn()
            await self.set(key, result, ttl_seconds)
            return result

        acquired = await self.redis.set(lock_key, "1", nx=True, ex=30)
        if not acquired:
            # Another coroutine is fetching — poll briefly
            for _ in range(10):
                await asyncio.sleep(1)
                cached = await self.get(key)
                if cached is not None:
                    return cached
            # Give up waiting, fetch ourselves
        try:
            result = await fetch_fn()
            await self.set(key, result, ttl_seconds)
            return result
        finally:
            await self.redis.delete(lock_key)

    async def stats(self) -> dict:
        total_hits = sum(self._hits.values())
        total_misses = sum(self._misses.values())
        total = total_hits + total_misses
        hit_rate = round(total_hits / total, 3) if total else 0.0

        if self._using_memory:
            keys = list(self._memory.keys())
        else:
            cursor, keys = await self.redis.scan(cursor=0, count=1000)
        by_prefix: dict[str, int] = defaultdict(int)
        for k in keys:
            prefix = k.decode().split(":")[0] if isinstance(k, bytes) else k.split(":")[0]
            by_prefix[prefix] += 1

        return {
            "hit_rate": hit_rate,
            "total_keys": len(keys),
            "by_prefix": dict(by_prefix),
        }


def cached(ttl: int):
    """Decorator that caches an async method keyed on its first string argument."""
    def decorator(fn: Callable):
        import functools

        @functools.wraps(fn)
        async def wrapper(self, ticker: str, *args, **kwargs):
            from backend.services.cache import CacheTTL  # avoid circular at module level
            key = f"{fn.__name__}:{ticker}"
            cache: CacheManager = getattr(self, "_cache", None)
            if cache is None:
                return await fn(self, ticker, *args, **kwargs)
            return await cache.get_or_fetch(
                key, lambda: fn(self, ticker, *args, **kwargs), ttl
            )

        return wrapper
    return decorator
