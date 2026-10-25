from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis

from app.core.config import Settings


def build_redis(settings: Settings) -> "Redis":
    return Redis.from_url(str(settings.redis_url), decode_responses=True, health_check_interval=30)


def get_redis(request: Request) -> "Redis":
    client: Redis = request.app.state.redis
    return client


RedisDep = Annotated["Redis", Depends(get_redis)]
