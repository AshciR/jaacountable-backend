"""Abstract cache backend protocol."""
from typing import Protocol, runtime_checkable


@runtime_checkable
class CacheBackend(Protocol):
    """
    Protocol for cache backends.

    Implementations must support get/set/delete of string values.
    Storing strings (JSON) makes this protocol compatible with both
    in-memory and Redis backends without serialization changes at call sites.
    """

    async def get(self, key: str) -> str | None:
        """Return cached value for key, or None if missing/expired."""
        ...

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Store value under key with a TTL in seconds."""
        ...

    async def delete(self, key: str) -> None:
        """Remove a key from the cache."""
        ...

    def size(self) -> int:
        """Current number of cached entries."""
        ...
