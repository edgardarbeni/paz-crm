"""Async engine and session management.

Routers receive an `AsyncSession` through `get_session`; services own the transaction
boundary (`async with session.begin():` or explicit commit). The dependency only guarantees
that an uncommitted transaction is rolled back and the session is closed.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.audit.hooks import AuditedSession
from app.core.config import Settings


def build_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.async_database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,
        connect_args={
            "server_settings": {
                "application_name": settings.service_name,
                "statement_timeout": str(settings.database_statement_timeout_ms),
                "timezone": "UTC",
            }
        },
    )


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # AuditedSession records every ORM write in the immutable audit log (D-37).
    return async_sessionmaker(
        engine, expire_on_commit=False, autoflush=False, sync_session_class=AuditedSession
    )


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:
        try:
            yield session
        finally:
            if session.in_transaction():
                await session.rollback()


SessionDep = Annotated[AsyncSession, Depends(get_session)]
