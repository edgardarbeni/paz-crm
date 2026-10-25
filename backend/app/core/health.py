from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.core.db.session import SessionDep
from app.core.errors import PROBLEM_RESPONSES, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.redis import RedisDep

router = APIRouter(tags=["health"], responses=PROBLEM_RESPONSES)
logger = get_logger(__name__)


class HealthStatus(BaseModel):
    status: Literal["ok"]


class ReadinessStatus(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]
    redis: Literal["ok"]


@router.get("/health", operation_id="getHealth", summary="Liveness: el proceso responde")
async def health() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get(
    "/ready",
    operation_id="getReadiness",
    summary="Readiness: base de datos y Redis disponibles",
)
async def ready(session: SessionDep, redis: RedisDep) -> ReadinessStatus:
    failing = []
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("readiness_database_failed")
        failing.append("base de datos")
    try:
        await redis.ping()
    except Exception:
        logger.exception("readiness_redis_failed")
        failing.append("Redis")
    if failing:
        raise ServiceUnavailableError(f"Dependencias no disponibles: {', '.join(failing)}.")
    return ReadinessStatus(status="ok", database="ok", redis="ok")
