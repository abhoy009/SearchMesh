import pytest
from unittest.mock import AsyncMock, MagicMock
from src.infra.cache import SearchMeshCache

@pytest.mark.anyio
async def test_cache_get_hit():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = b"test_value"
    
    cache = SearchMeshCache(mock_redis)
    val = await cache.get("key")
    assert val == "test_value"
    mock_redis.get.assert_called_once_with("key")

@pytest.mark.anyio
async def test_cache_get_miss():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    
    cache = SearchMeshCache(mock_redis)
    val = await cache.get("key")
    assert val is None
    mock_redis.get.assert_called_once_with("key")

@pytest.mark.anyio
async def test_cache_get_error_graceful():
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = Exception("Redis connection lost")
    
    cache = SearchMeshCache(mock_redis)
    val = await cache.get("key")
    # Should fail open and return None instead of raising
    assert val is None

@pytest.mark.anyio
async def test_cache_set():
    mock_redis = AsyncMock()
    cache = SearchMeshCache(mock_redis)
    await cache.set("key", "value", 100)
    mock_redis.setex.assert_called_once_with("key", 100, "value")

@pytest.mark.anyio
async def test_cache_set_error_graceful():
    mock_redis = AsyncMock()
    mock_redis.setex.side_effect = Exception("Write failed")
    
    cache = SearchMeshCache(mock_redis)
    # Should not raise exception
    await cache.set("key", "value", 100)

@pytest.mark.anyio
async def test_cache_delete_pattern():
    mock_redis = AsyncMock()
    mock_redis.keys.return_value = [b"key1", b"key2"]
    mock_redis.delete.return_value = 2
    
    cache = SearchMeshCache(mock_redis)
    res = await cache.delete_pattern("search:*")
    assert res == 2
    mock_redis.keys.assert_called_once_with("search:*")
    mock_redis.delete.assert_called_once_with(b"key1", b"key2")

@pytest.mark.anyio
async def test_cache_delete_pattern_empty():
    mock_redis = AsyncMock()
    mock_redis.keys.return_value = []
    
    cache = SearchMeshCache(mock_redis)
    res = await cache.delete_pattern("search:*")
    assert res == 0
    mock_redis.keys.assert_called_once_with("search:*")
    mock_redis.delete.assert_not_called()

def test_key_generation_deterministic():
    cache = SearchMeshCache(None)
    key1 = cache._search_key("Hello World")
    key2 = cache._search_key("hello world ")
    # Normalization (strip & lower) makes these identical
    assert key1 == key2
    
    key3 = cache._fetch_key("https://example.com")
    key4 = cache._fetch_key("https://example.com ")
    assert key3 == key4
