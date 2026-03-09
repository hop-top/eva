# tests/unit/test_state.py
"""Tests for RedisStateAdapter using mock_redis fixture."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_mock_redis_get(mock_redis):
    result = await mock_redis.get("some-key")
    assert result is None
    mock_redis.get.assert_awaited_once_with("some-key")


@pytest.mark.asyncio
async def test_mock_redis_set(mock_redis):
    await mock_redis.set("k", "v", ttl=60)
    mock_redis.set.assert_awaited_once_with("k", "v", ttl=60)


@pytest.mark.asyncio
async def test_mock_redis_delete(mock_redis):
    await mock_redis.delete("k")
    mock_redis.delete.assert_awaited_once_with("k")


def _make_adapter_with_fake_client(fake_client):
    """Build a RedisStateAdapter injecting a fake client directly."""
    from core.state import RedisStateAdapter

    adapter = object.__new__(RedisStateAdapter)
    adapter._client = fake_client
    return adapter


@pytest.mark.asyncio
async def test_redis_state_adapter_get():
    """Unit test RedisStateAdapter.get without real Redis."""
    import json

    fake_client = AsyncMock()
    fake_client.get = AsyncMock(return_value=json.dumps({"x": 1}))
    adapter = _make_adapter_with_fake_client(fake_client)

    result = await adapter.get("mykey")
    assert result == {"x": 1}


@pytest.mark.asyncio
async def test_redis_state_adapter_get_none():
    fake_client = AsyncMock()
    fake_client.get = AsyncMock(return_value=None)
    adapter = _make_adapter_with_fake_client(fake_client)

    result = await adapter.get("missing")
    assert result is None


@pytest.mark.asyncio
async def test_redis_state_adapter_set_no_ttl():
    import json

    fake_client = AsyncMock()
    fake_client.set = AsyncMock(return_value=True)
    adapter = _make_adapter_with_fake_client(fake_client)

    await adapter.set("k", {"score": 0.9})
    fake_client.set.assert_awaited_once_with("k", json.dumps({"score": 0.9}))


@pytest.mark.asyncio
async def test_redis_state_adapter_set_with_ttl():
    import json

    fake_client = AsyncMock()
    fake_client.setex = AsyncMock(return_value=True)
    adapter = _make_adapter_with_fake_client(fake_client)

    await adapter.set("k", "hello", ttl=30)
    fake_client.setex.assert_awaited_once_with("k", 30, json.dumps("hello"))


@pytest.mark.asyncio
async def test_redis_state_adapter_delete():
    fake_client = AsyncMock()
    fake_client.delete = AsyncMock(return_value=1)
    adapter = _make_adapter_with_fake_client(fake_client)

    await adapter.delete("k")
    fake_client.delete.assert_awaited_once_with("k")
