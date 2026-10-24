"""Uniform error responses following RFC 9457 (Problem Details for HTTP APIs).

Services raise `AppError` subclasses; routers never build error responses by hand.
"""

from http import HTTPStatus
from typing import Any, ClassVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import get_context
from app.core.logging import get_logger

PROBLEM_CONTENT_TYPE = "application/problem+json"
PROBLEM_TYPE_PREFIX = "urn:pazos:problem:"

logger = get_logger(__name__)


class FieldViolation(BaseModel):
    field: str = Field(description="Dotted path of the offending field, e.g. 'body.email'.")
    message: str
    code: str


class Problem(BaseModel):
    """RFC 9457 problem document. `code` and `request_id` are extension members."""

    type: str = Field(examples=["urn:pazos:problem:validation-error"])
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    code: str
    request_id: str | None = None
    errors: list[FieldViolation] | None = None


class AppError(Exception):
    status: ClassVar[HTTPStatus] = HTTPStatus.INTERNAL_SERVER_ERROR
    code: ClassVar[str] = "internal-error"
    title: ClassVar[str] = "Error interno"

    def __init__(self, detail: str | None = None, *, extra: dict[str, Any] | None = None):
        super().__init__(detail or self.title)
        self.detail = detail
        self.extra = extra or {}


class BadRequestError(AppError):
    status = HTTPStatus.BAD_REQUEST
    code = "bad-request"
    title = "Solicitud inválida"


class NotFoundError(AppError):
    status = HTTPStatus.NOT_FOUND
    code = "not-found"
    title = "Recurso no encontrado"


class ConflictError(AppError):
    status = HTTPStatus.CONFLICT
    code = "conflict"
    title = "Conflicto con el estado actual del recurso"


class ServiceUnavailableError(AppError):
    status = HTTPStatus.SERVICE_UNAVAILABLE
    code = "service-unavailable"
    title = "Servicio no disponible"


def problem_response(
    request: Request,
    *,
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
    errors: list[FieldViolation] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    problem = Problem(
        type=f"{PROBLEM_TYPE_PREFIX}{code}",
        title=title,
        status=status,
        detail=detail,
        instance=request.url.path,
        code=code,
        request_id=get_context().request_id,
        errors=errors,
    )
    return JSONResponse(
        problem.model_dump(exclude_none=True),
        status_code=status,
        media_type=PROBLEM_CONTENT_TYPE,
        headers=headers,
    )


async def _app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)  # noqa: S101 - registered only for AppError
    if exc.status >= HTTPStatus.INTERNAL_SERVER_ERROR:
        logger.error("app_error", code=exc.code, detail=exc.detail)
    return problem_response(
        request, status=exc.status, code=exc.code, title=exc.title, detail=exc.detail
    )


_HTTP_TITLES: dict[int, str] = {
    400: "Solicitud inválida",
    401: "No autenticado",
    403: "Acceso denegado",
    404: "Recurso no encontrado",
    405: "Método no permitido",
    409: "Conflicto con el estado actual del recurso",
    413: "Contenido demasiado grande",
    415: "Tipo de contenido no soportado",
    422: "Datos inválidos",
    429: "Demasiadas solicitudes",
}


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    status = HTTPStatus(exc.status_code)
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail != status.phrase else None
    return problem_response(
        request,
        status=status,
        code=status.phrase.lower().replace(" ", "-"),
        title=_HTTP_TITLES.get(status, status.phrase),
        detail=detail,
        headers=getattr(exc, "headers", None),
    )


async def _validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    violations = [
        FieldViolation(
            field=".".join(str(part) for part in error.get("loc", ())),
            message=str(error.get("msg", "")),
            code=str(error.get("type", "invalid")),
        )
        for error in exc.errors()
    ]
    return problem_response(
        request,
        status=HTTPStatus.UNPROCESSABLE_ENTITY,
        code="validation-error",
        title="Datos inválidos",
        detail="Uno o más campos no son válidos.",
        errors=violations,
    )


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", error_type=type(exc).__name__)
    return problem_response(
        request,
        status=HTTPStatus.INTERNAL_SERVER_ERROR,
        code=AppError.code,
        title=AppError.title,
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)


PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    "4XX": {"model": Problem, "description": "Error del cliente (RFC 9457)"},
    "5XX": {"model": Problem, "description": "Error del servidor (RFC 9457)"},
}
"""Attach to routers so every operation documents its Problem Details responses."""


def install_problem_openapi(app: FastAPI) -> None:
    """FastAPI documents `model` responses as application/json; Problem Details are served as
    application/problem+json, so error responses are rewritten in the generated schema."""
    original = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = original()
        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                for status, response in operation.get("responses", {}).items():
                    content = response.get("content", {})
                    if status[0] in "45" and "application/json" in content:
                        content[PROBLEM_CONTENT_TYPE] = content.pop("application/json")
        app.openapi_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]
