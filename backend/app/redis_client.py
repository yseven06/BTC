"""
Async Redis client for Upstash with caching helpers.

Provides connection management and convenience functions for
get/set/delete operations with TTL support and JSON serialization.
"""

import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Module-level client reference, initialized on startup
_redis_client: Optional[aioredis.Redis] = None

# Default TTL values in seconds
DEFAULT_TTL = 300  # 5 minutes
PRICE_TTL = 60  # 1 minute for price data
SIGNAL_TTL = 900  # 15 minutes for signals
ANALYSIS_TTL = 1800  # 30 minutes for analysis results
USER_TTL = 600  # 10 minutes for user data


async def get_redis() -> aioredis.Redis:
    """
    Get or create the async Redis client singleton.

    Returns:
        aioredis.Redis: The connected Redis client instance.

    Raises:
        ConnectionError: If unable to connect to Redis.
    """
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = aioredis.from_url(
                settings.UPSTASH_REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
                retry_on_timeout=True,
            )
            # Verify the connection
            await _redis_client.ping()
            logger.info("Redis connection established successfully.")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", str(e))
            raise ConnectionError(f"Redis connection failed: {e}") from e
    return _redis_client


async def close_redis() -> None:
    """Close the Redis connection gracefully."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
        logger.info("Redis connection closed.")


async def cache_get(key: str) -> Optional[Any]:
    """
    Retrieve a value from the cache.

    Automatically deserializes JSON-encoded values back to Python objects.

    Args:
        key: The cache key to look up.

    Returns:
        The cached value, or None if the key does not exist or on error.
    """
    try:
        client = await get_redis()
        value = await client.get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    except Exception as e:
        logger.warning("Redis GET error for key '%s': %s", key, str(e))
        return None


async def cache_set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> bool:
    """
    Store a value in the cache with a time-to-live.

    Automatically serializes Python objects to JSON.

    Args:
        key: The cache key.
        value: The value to cache (must be JSON-serializable).
        ttl: Time-to-live in seconds (default: 300).

    Returns:
        True if the value was successfully cached, False on error.
    """
    try:
        client = await get_redis()
        if isinstance(value, (dict, list, tuple)):
            serialized = json.dumps(value, default=str)
        elif isinstance(value, (int, float, bool)):
            serialized = json.dumps(value)
        else:
            serialized = str(value)
        await client.set(key, serialized, ex=ttl)
        return True
    except Exception as e:
        logger.warning("Redis SET error for key '%s': %s", key, str(e))
        return False


async def cache_delete(key: str) -> bool:
    """
    Delete a key from the cache.

    Args:
        key: The cache key to delete.

    Returns:
        True if the key was deleted, False on error.
    """
    try:
        client = await get_redis()
        await client.delete(key)
        return True
    except Exception as e:
        logger.warning("Redis DELETE error for key '%s': %s", key, str(e))
        return False


async def cache_delete_pattern(pattern: str) -> int:
    """
    Delete all keys matching a glob pattern.

    Args:
        pattern: Glob-style pattern (e.g., 'signals:*').

    Returns:
        The number of keys deleted.
    """
    try:
        client = await get_redis()
        deleted = 0
        async for key in client.scan_iter(match=pattern, count=100):
            await client.delete(key)
            deleted += 1
        return deleted
    except Exception as e:
        logger.warning("Redis DELETE PATTERN error for '%s': %s", pattern, str(e))
        return 0


async def cache_exists(key: str) -> bool:
    """
    Check whether a key exists in the cache.

    Args:
        key: The cache key.

    Returns:
        True if the key exists, False otherwise or on error.
    """
    try:
        client = await get_redis()
        return bool(await client.exists(key))
    except Exception as e:
        logger.warning("Redis EXISTS error for key '%s': %s", key, str(e))
        return False


async def cache_set_hash(key: str, mapping: dict, ttl: int = DEFAULT_TTL) -> bool:
    """
    Store a hash (dictionary) in the cache.

    Args:
        key: The cache key for the hash.
        mapping: Dictionary of field-value pairs.
        ttl: Time-to-live in seconds.

    Returns:
        True on success, False on error.
    """
    try:
        client = await get_redis()
        serialized = {k: json.dumps(v, default=str) if isinstance(v, (dict, list)) else str(v)
                      for k, v in mapping.items()}
        await client.hset(key, mapping=serialized)
        await client.expire(key, ttl)
        return True
    except Exception as e:
        logger.warning("Redis HSET error for key '%s': %s", key, str(e))
        return False


async def cache_get_hash(key: str) -> Optional[dict]:
    """
    Retrieve an entire hash from the cache.

    Args:
        key: The cache key for the hash.

    Returns:
        Dictionary of field-value pairs, or None on error.
    """
    try:
        client = await get_redis()
        data = await client.hgetall(key)
        if not data:
            return None
        result = {}
        for k, v in data.items():
            try:
                result[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                result[k] = v
        return result
    except Exception as e:
        logger.warning("Redis HGETALL error for key '%s': %s", key, str(e))
        return None


async def cache_increment(key: str, amount: int = 1, ttl: int = DEFAULT_TTL) -> Optional[int]:
    """
    Atomically increment a counter in the cache.

    Args:
        key: The counter key.
        amount: Increment amount (default: 1).
        ttl: Time-to-live in seconds (set only on first creation).

    Returns:
        The new counter value, or None on error.
    """
    try:
        client = await get_redis()
        value = await client.incrby(key, amount)
        if value == amount:
            await client.expire(key, ttl)
        return value
    except Exception as e:
        logger.warning("Redis INCR error for key '%s': %s", key, str(e))
        return None
