"""Problem Details, request id, security headers, CORS and docs toggling — no services needed."""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.core.errors import ConflictError, NotFoundError
from app.main import create_app
from tests.support import make_settings


class Payload(BaseModel):
    email: str
    age: int


def build_app(**overrides: object) -> FastAPI:
    app = create_app(make_settings(**overrides))

    @app.get("/boom/not-found")
    async def not_found() -> None:
        raise NotFoundError("La sección 9999 no existe.")

    @app.get("/boom/conflict")
    async def conflict() -> None:
        raise ConflictError()

    @app.get("/boom/http")
    async def http_error() -> None:
        raise HTTPException(status_code=403, detail="Sin permiso")

    @app.get("/boom/crash")
    async def crash() -> None:
        raise RuntimeError("secret internals")

    @app.post("/boom/validate")
    async def validate(payload: Payload) -> Payload:
        return payload

    return app


@pytest.fixture
async def http() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=build_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_app_error_is_problem_details(http: AsyncClient) -> None:
    response = await http.get("/boom/not-found")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body == {
        "type": "urn:pazos:problem:not-found",
        "title": "Recurso no encontrado",
        "status": 404,
        "detail": "La sección 9999 no existe.",
        "instance": "/boom/not-found",
        "code": "not-found",
        "request_id": response.headers["x-request-id"],
    }


async def test_app_error_without_detail(http: AsyncClient) -> None:
    body = (await http.get("/boom/conflict")).json()
    assert body["status"] == 409
    assert "detail" not in body


async def test_http_exception_and_unknown_route(http: AsyncClient) -> None:
    forbidden = (await http.get("/boom/http")).json()
    assert (forbidden["status"], forbidden["code"], forbidden["detail"]) == (
        403,
        "forbidden",
        "Sin permiso",
    )
    assert forbidden["title"] == "Acceso denegado"
    missing = await http.get("/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["title"] == "Recurso no encontrado"
    not_allowed = (await http.delete("/health")).json()
    assert (not_allowed["status"], not_allowed["title"]) == (405, "Método no permitido")
    assert missing.json()["code"] == "not-found"
    assert "detail" not in missing.json()


async def test_validation_error_lists_fields(http: AsyncClient) -> None:
    response = await http.post("/boom/validate", json={"email": "a@b.mx", "age": "x"})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation-error"
    assert body["errors"] == [
        {"field": "body.age", "message": body["errors"][0]["message"], "code": "int_parsing"}
    ]


async def test_unhandled_error_does_not_leak(http: AsyncClient) -> None:
    response = await http.get("/boom/crash")
    assert response.status_code == 500
    assert "secret" not in response.text
    assert response.json()["code"] == "internal-error"


async def test_request_id_is_generated_or_propagated(http: AsyncClient) -> None:
    generated = (await http.get("/health")).headers["x-request-id"]
    assert len(generated) == 36
    propagated = await http.get("/health", headers={"X-Request-ID": "abc-123-def-456"})
    assert propagated.headers["x-request-id"] == "abc-123-def-456"
    rejected = await http.get("/health", headers={"X-Request-ID": "bad id\nwith newline"})
    assert rejected.headers["x-request-id"] != "bad id\nwith newline"


async def test_security_headers(http: AsyncClient) -> None:
    api = await http.get("/health")
    assert api.headers["x-content-type-options"] == "nosniff"
    assert api.headers["x-frame-options"] == "DENY"
    assert api.headers["cache-control"] == "no-store"
    assert api.headers["content-security-policy"].startswith("default-src 'none'")
    assert "strict-transport-security" not in api.headers
    docs = await http.get("/docs")
    assert "cdn.jsdelivr.net" in docs.headers["content-security-policy"]
    assert "cache-control" not in docs.headers


async def test_hsts_only_in_production() -> None:
    app = create_app(make_settings(environment="production"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        response = await client.get("/health")
    assert response.headers["strict-transport-security"].startswith("max-age=")


async def test_cors_allows_only_configured_origins(http: AsyncClient) -> None:
    allowed = await http.options(
        "/health",
        headers={"Origin": "https://panel.test", "Access-Control-Request-Method": "GET"},
    )
    assert allowed.headers["access-control-allow-origin"] == "https://panel.test"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    denied = await http.get("/health", headers={"Origin": "https://evil.test"})
    assert "access-control-allow-origin" not in denied.headers


async def test_docs_can_be_disabled() -> None:
    app = create_app(make_settings(api_docs_enabled=False))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/docs")).status_code == 404
        assert (await client.get("/openapi.json")).status_code == 404


def test_openapi_documents_problem_responses() -> None:
    schema = create_app(make_settings()).openapi()
    ready = schema["paths"]["/ready"]["get"]
    assert ready["operationId"] == "getReadiness"
    for status in ("4XX", "5XX"):
        content = ready["responses"][status]["content"]
        assert content == {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/Problem"}}
        }
    assert ready["responses"]["200"]["content"].keys() == {"application/json"}
    app = create_app(make_settings())
    assert app.openapi() is app.openapi()  # cached after the first build


def test_settings_parsing() -> None:
    settings = make_settings(
        cors_allowed_origins="https://a.mx, https://b.mx,",
        database_url="postgres://u:p@h:5432/db",
    )
    assert settings.cors_allowed_origins == ["https://a.mx", "https://b.mx"]
    assert settings.async_database_url.startswith("postgresql+asyncpg://")
    assert settings.async_migrations_database_url == settings.async_database_url
    assert not settings.is_production
