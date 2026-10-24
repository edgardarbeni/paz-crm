"""Per-request context shared by logging, auditing and authorization.

Populated by the request middleware (request id, client ip, user agent) and, from phase B on,
by the authentication dependency (actor). Background jobs and CLI commands set it explicitly.
"""

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    actor_user_id: uuid.UUID | None = None


_current: ContextVar[RequestContext] = ContextVar(
    "paz_request_context",
    default=RequestContext(),  # noqa: B039 - frozen dataclass, safe to share
)


def get_context() -> RequestContext:
    return _current.get()


def set_context(context: RequestContext) -> None:
    _current.set(context)


def bind_actor(actor_user_id: uuid.UUID | None) -> None:
    _current.set(replace(_current.get(), actor_user_id=actor_user_id))
