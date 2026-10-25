"""Fixed-window rate limiting on Redis (CLAUDE.md: per IP and per user)."""

import hashlib

from redis.asyncio import Redis

from app.core.errors import TooManyRequestsError


class RateLimiter:
    def __init__(self, redis: "Redis", *, prefix: str = "rl") -> None:
        self._redis = redis
        self._prefix = prefix

    async def hit(self, bucket: str, identity: str, *, limit: int, window_seconds: int) -> None:
        """Counts one hit; raises 429 (with Retry-After) when `limit` is exceeded."""
        key = f"{self._prefix}:{bucket}:{_digest(identity)}"
        pipeline = self._redis.pipeline()
        pipeline.incr(key)
        pipeline.expire(key, window_seconds, nx=True)
        pipeline.ttl(key)
        count, _, ttl = await pipeline.execute()
        if int(count) > limit:
            retry_after = max(int(ttl), 1)
            raise TooManyRequestsError(
                "Demasiados intentos. Intenta de nuevo más tarde.",
                headers={"Retry-After": str(retry_after)},
            )

    async def reset(self, bucket: str, identity: str) -> None:
        await self._redis.delete(f"{self._prefix}:{bucket}:{_digest(identity)}")


def _digest(identity: str) -> str:
    # Keys never contain raw e-mails or IPs.
    return hashlib.sha256(identity.strip().lower().encode()).hexdigest()[:32]
