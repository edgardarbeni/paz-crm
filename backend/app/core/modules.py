"""Module registry: a new module is a package under `app/modules/` with a `module.py` that
declares a `MODULE = ModuleSpec(...)`. The API, Alembic, the model metadata and the permission
catalog read the registry, so adding a module does not touch the core (architecture.md §8,
difference 2).

References are strings ("package.module:attribute") resolved on demand, so importing the
registry never imports routers or models and cannot create import cycles.
"""

import pkgutil
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from importlib import import_module
from typing import Any

from fastapi import APIRouter

MODULES_PACKAGE = "app.modules"


@dataclass(frozen=True, slots=True)
class ModuleSpec:
    name: str
    # Mounting order of the routers (and of their tags in OpenAPI).
    order: int
    # PostgreSQL schema whose tables Alembic autogenerate manages.
    schema: str | None = None
    # Dotted module that defines the table models.
    models: str | None = None
    # "package.module:attribute" of each APIRouter, mounted under /api/v1.
    routers: tuple[str, ...] = ()
    # "package.module:Enum" with the module's permission codes (`<module>.<resource>.<action>`).
    permissions: str | None = None
    # Dotted module imported once at startup to register hooks in other modules (e.g. people).
    setup: str | None = None


def _resolve(reference: str) -> Any:
    module, _, attribute = reference.partition(":")
    return getattr(import_module(module), attribute)


@cache
def installed_modules() -> tuple[ModuleSpec, ...]:
    package = import_module(MODULES_PACKAGE)
    specs: list[ModuleSpec] = []
    for info in pkgutil.iter_modules(package.__path__):
        name = f"{MODULES_PACKAGE}.{info.name}.module"
        try:
            declared = import_module(name)
        except ModuleNotFoundError as error:
            if error.name == name:
                continue  # a package without module.py is not a module (e.g. helpers)
            raise
        specs.append(declared.MODULE)
    return tuple(sorted(specs, key=lambda spec: (spec.order, spec.name)))


def managed_schemas() -> set[str]:
    return {spec.schema for spec in installed_modules() if spec.schema}


def import_models() -> None:
    for spec in installed_modules():
        if spec.models:
            import_module(spec.models)


@cache
def setup_modules() -> None:
    """Imports each module's `setup` (API startup, CLI and tests). Idempotent."""
    for spec in installed_modules():
        if spec.setup:
            import_module(spec.setup)


def api_routers() -> list[APIRouter]:
    return [_resolve(ref) for spec in installed_modules() for ref in spec.routers]


@cache
def permission_codes() -> frozenset[str]:
    """Every permission declared by an installed module; migrations seed the same codes."""
    codes: set[str] = set()
    for spec in installed_modules():
        if spec.permissions:
            enum: type[StrEnum] = _resolve(spec.permissions)
            codes.update(member.value for member in enum)
    return frozenset(codes)
