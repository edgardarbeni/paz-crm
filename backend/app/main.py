"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import health
from app.core.config import Environment, Settings, get_settings
from app.core.db.session import build_engine, build_sessionmaker
from app.core.errors import PROBLEM_RESPONSES, install_problem_openapi, register_error_handlers
from app.core.logging import configure_logging
from app.core.mail import Mailer, build_mailer
from app.core.middleware import (
    REQUEST_ID_HEADER,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.redis import build_redis
from app.core.telemetry import configure_telemetry
from app.modules.audit import router as audit_router
from app.modules.geography import router as geography_router
from app.modules.identity.container import build_identity_services
from app.modules.identity.routers import admin as identity_admin
from app.modules.identity.routers import auth as identity_auth

API_PREFIX = "/api/v1"


def build_api_router() -> APIRouter:
    """Module routers are mounted here as each phase adds them."""
    router = APIRouter(prefix=API_PREFIX, responses=PROBLEM_RESPONSES)
    router.include_router(identity_auth.router)
    router.include_router(identity_admin.users_router)
    router.include_router(identity_admin.roles_router)
    router.include_router(audit_router.router)
    router.include_router(geography_router.router)
    return router


def create_app(settings: Settings | None = None, *, mailer: Mailer | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, json=settings.environment is not Environment.DEVELOPMENT)

    engine = build_engine(settings)
    redis = build_redis(settings)
    mailer = mailer or build_mailer(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.engine = engine
        app.state.sessionmaker = build_sessionmaker(engine)
        app.state.redis = redis
        app.state.mailer = mailer
        app.state.identity = build_identity_services(settings, redis, mailer)
        try:
            yield
        finally:
            await redis.aclose()
            await engine.dispose()

    docs = settings.api_docs_enabled
    app = FastAPI(
        title="PAZOS API",
        version="0.1.0",
        description="API del sistema PAZOS. Errores en formato RFC 9457 (Problem Details).",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )

    register_error_handlers(app)
    install_problem_openapi(app)

    # Last added runs first: request context wraps everything.
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
        max_age=600,
    )
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router)
    app.include_router(build_api_router())

    configure_telemetry(app, engine, settings)
    return app
