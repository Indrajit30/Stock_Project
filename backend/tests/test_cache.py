import pytest

from backend.services.cache import CacheManager


@pytest.mark.asyncio
async def test_set_and_get():
    cache = CacheManager()
    await cache.connect()
    await cache.set("test:key", {"hello": "world"}, ttl_seconds=60)
    result = await cache.get("test:key")
    assert result == {"hello": "world"}
    await cache.close()


@pytest.mark.asyncio
async def test_cache_miss_returns_none():
    cache = CacheManager()
    await cache.connect()
    result = await cache.get("test:nonexistent:key:xyz")
    assert result is None
    await cache.close()
