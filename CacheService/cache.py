"""
Reusable cache service for Django applications.
- Works with any Django cache backend (Redis, Dummy, LocMem, Memcached, etc.).
- Uses a consistent key pattern: {prefix}:{schema}:{table}:{key}.
- Supports get, set, and invalidate operations.
- Provides optional advanced operations when the backend supports key scanning (e.g., django-redis).
"""

from typing import Any, List, Optional, Callable
import json
import logging
from django.core.cache import caches

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Key Builder
# --------------------------------------------------------------------------

DEFAULT_PREFIX = "kv"


def build_key(
    key: Any,
    table: Optional[str] = None,
    schema: Optional[str] = None,
    prefix: str = DEFAULT_PREFIX,
) -> str:
    """
    Build a consistent cache key.

    Example:
        build_key(42, "customer", "tenant1") -> "kv:tenant1:customer:42"
    """
    if key is None:
        raise ValueError("key must not be None")
    parts = [prefix, schema, table, key]
    return ":".join(str(p) for p in parts if p is not None)


# --------------------------------------------------------------------------
# Base Interface (Blueprint)
# --------------------------------------------------------------------------

class BaseCache:
    """
    Abstract class that defines what any cache backend must support.
    """

    def get(self, key: str) -> Any:
        raise NotImplementedError

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError


# --------------------------------------------------------------------------
# Django Cache Backend Wrapper
# --------------------------------------------------------------------------

def _default_serialize(value: Any) -> Any:
    """
    Try JSON first; if it fails, fall back to the raw value (letting the backend handle it).
    """
    try:
        return json.dumps(value)
    except Exception:
        return value


def _default_deserialize(value: Any) -> Any:
    """
    Try JSON decode; if it fails, return the raw value.
    """
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode()
        except Exception:
            # Leave bytes as-is if decode fails
            return value
    try:
        return json.loads(value)
    except Exception:
        return value


class DjangoCacheBackend(BaseCache):
    def __init__(
        self,
        alias: str = "default",
        serializer: Optional[Callable[[Any], Any]] = None,
        deserializer: Optional[Callable[[Any], Any]] = None,
    ):
        self._cache = caches[alias]
        self._serialize = serializer or _default_serialize
        self._deserialize = deserializer or _default_deserialize

    def get(self, key: str) -> Any:
        try:
            raw = self._cache.get(key)
        except Exception as exc:
            logger.exception("Cache get failed for key=%s: %s", key, exc)
            return None
        return self._deserialize(raw)

    def set(self, key: str, value: Any, ttl: Optional[int] = 3600) -> None:
        try:
            payload = self._serialize(value)
        except Exception as exc:
            logger.exception("Serialization failed for key=%s: %s", key, exc)
            payload = value  # best-effort fallback
        try:
            self._cache.set(key, payload, timeout=ttl)
        except Exception as exc:
            logger.exception("Cache set failed for key=%s: %s", key, exc)

    def delete(self, key: str) -> None:
        try:
            self._cache.delete(key)
        except Exception as exc:
            logger.exception("Cache delete failed for key=%s: %s", key, exc)

    # ------------------------------------------------------------------
    # Redis-specific utilities
    # ------------------------------------------------------------------
    def keys(self, pattern: str = "*") -> List[str]:
        """
        Return all cache keys matching a given pattern.
        Works with Redis (django-redis); returns [] for unsupported backends.
        """
        if hasattr(self._cache, "iter_keys"):
            try:
                return list(self._cache.iter_keys(pattern))
            except Exception as exc:
                logger.exception("Cache iter_keys failed for pattern=%s: %s", pattern, exc)
                return []
        return []

    def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching a pattern.
        Works with Redis (django-redis); no-op for unsupported backends.
        """
        if hasattr(self._cache, "delete_pattern"):
            try:
                deleted = self._cache.delete_pattern(pattern)
                return int(deleted or 0)
            except Exception as exc:
                logger.exception("Cache delete_pattern failed for pattern=%s: %s", pattern, exc)
                return 0
        return 0


# --------------------------------------------------------------------------
# Cache Service (Main Class to Use Everywhere)
# --------------------------------------------------------------------------

class CacheService:
    """
    Main service class that your application will use.

    It hides the key-building logic and provides:
      - get(key, table, schema)
      - set(key, table, schema, value)
      - invalidate_by_id(key, table, schema)
    """

    def __init__(self, backend: BaseCache = DjangoCacheBackend(alias="default")):
        self.backend = backend

    # ------------------------------
    # Key builder
    # ------------------------------
    def key(
        self,
        key: Any,
        table: Optional[str] = None,
        schema: Optional[str] = None,
        prefix: str = DEFAULT_PREFIX,
    ) -> str:
        return build_key(key=key, table=table, schema=schema, prefix=prefix)

    # ------------------------------
    # Cache operations
    # ------------------------------

    def get(
        self,
        key: Any,
        table: Optional[str] = None,
        schema: Optional[str] = None,
        prefix: str = DEFAULT_PREFIX,
    ) -> Any:
        """
        Get value from cache using (key, table, schema).
        Returns None if not found or on backend failure.
        """
        return self.backend.get(self.key(key, table, schema, prefix))

    def set(
        self,
        key: Any,
        value: Any,
        table: Optional[str] = None,
        schema: Optional[str] = None,
        ttl: Optional[int] = 3600,
        prefix: str = DEFAULT_PREFIX,
    ) -> None:
        """
        Save value in cache for given (key, table, schema).
        ttl = time in seconds before cache expires (optional).
        """
        if ttl is not None and ttl < 0:
            ttl = None  # treat negative as no-expiry
        self.backend.set(self.key(key, table, schema, prefix), value, ttl=ttl)

    def invalidate_by_id(
        self,
        key: Any,
        table: Optional[str] = None,
        schema: Optional[str] = None,
        prefix: str = DEFAULT_PREFIX,
    ) -> None:
        """
        Remove cache entry for given (key, table, schema).
        Call this whenever a record is updated/deleted in DB.
        """
        self.backend.delete(self.key(key, table, schema, prefix))

    # ------------------------------------------------------------------
    # Advanced cache operations (require backend support for key scan)
    # ------------------------------------------------------------------
    def get_all_by_schema(
        self, schema: str, prefix: str = DEFAULT_PREFIX
    ) -> List[str]:
        """Return all keys in cache for a given schema."""
        pattern = f"{prefix}:{schema}:*"
        return self.backend.keys(pattern)

    def invalidate_all_by_schema(
        self, schema: str, prefix: str = DEFAULT_PREFIX
    ) -> int:
        """Invalidate all cache entries for a given schema."""
        pattern = f"{prefix}:{schema}:*"
        return self.backend.delete_pattern(pattern)

    def invalidate_all_by_table(
        self,
        table: str,
        schema: Optional[str] = None,
        prefix: str = DEFAULT_PREFIX,
    ) -> int:
        """Invalidate all keys for a specific table (optionally within a schema)."""
        if schema:
            pattern = f"{prefix}:{schema}:{table}:*"
        else:
            pattern = f"{prefix}:*:{table}:*"
        return self.backend.delete_pattern(pattern)

    def invalidate_all_by_key(
        self, key_fragment: str, prefix: str = DEFAULT_PREFIX
    ) -> int:
        """Invalidate all keys containing the given key fragment."""
        pattern = f"*{key_fragment}*"
        return self.backend.delete_pattern(pattern)

    def count_keys(
        self, schema: Optional[str] = None, prefix: str = DEFAULT_PREFIX
    ) -> int:
        """Count total number of keys, or keys within a schema."""
        pattern = f"{prefix}:{schema}:*" if schema else "*"
        return len(self.backend.keys(pattern))

    def get_all_keys(
        self, schema: Optional[str] = None, prefix: str = DEFAULT_PREFIX
    ) -> List[str]:
        """Return all keys, or keys within a schema."""
        pattern = f"{prefix}:{schema}:*" if schema else "*"
        return self.backend.keys(pattern)