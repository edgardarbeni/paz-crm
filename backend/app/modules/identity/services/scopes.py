"""Geographic scope (D-34): what part of the country a user may see and act on.

- A user's scopes are nodes (national, region, state, DF, DL, municipality, section).
- They resolve to a set of sections, materialized in `user_scope_sections` for non-national
  scopes; repositories filter with EXISTS against it (query layer, not only endpoints).
- `grants_all` (superadmin) and a `national` scope see everything. No scope = sees nothing
  (deny by default).
- Nobody can hand out a scope wider than their own (geographic anti-escalation).
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, delete, exists, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped
from sqlmodel import col

from app.core.errors import BadRequestError, ForbiddenError, NotFoundError
from app.modules.identity import repository as repo
from app.modules.identity.models import SCOPE_COLUMNS, ScopeLevel, UserScope, UserScopeSection
from app.modules.identity.services.access import Access, load_access

# Level → (geography table, column in geography.sections that links to it, or None for itself)
_LEVEL_TABLES: dict[ScopeLevel, tuple[str, str | None]] = {
    ScopeLevel.ELECTORAL_REGION: ("electoral_regions", None),
    ScopeLevel.STATE: ("states", "state_id"),
    ScopeLevel.FEDERAL_DISTRICT: ("federal_districts", "federal_district_id"),
    ScopeLevel.LOCAL_DISTRICT: ("local_districts", "local_district_id"),
    ScopeLevel.MUNICIPALITY: ("municipalities", "municipality_id"),
    ScopeLevel.SECTION: ("sections", "id"),
}


SectionColumn = ColumnElement[Any] | Mapped[Any]


@dataclass(frozen=True, slots=True)
class GeoScope:
    """Resolved scope of a user for the current request."""

    user_id: uuid.UUID
    unrestricted: bool

    def sections_filter(self, section_id: SectionColumn) -> ColumnElement[bool] | None:
        """EXISTS clause limiting `section_id` to the user's sections (None = no filter)."""
        if self.unrestricted:
            return None
        return exists().where(
            col(UserScopeSection.user_id) == self.user_id,
            col(UserScopeSection.section_id) == section_id,
        )


async def resolve_scope(db: AsyncSession, user_id: uuid.UUID, access: Access) -> GeoScope:
    if access.grants_all:
        return GeoScope(user_id=user_id, unrestricted=True)
    national = (
        await db.execute(
            select(col(UserScope.id)).where(
                col(UserScope.user_id) == user_id, col(UserScope.scope_level) == ScopeLevel.NATIONAL
            )
        )
    ).first()
    return GeoScope(user_id=user_id, unrestricted=national is not None)


async def scopes_of(db: AsyncSession, user_id: uuid.UUID) -> list[UserScope]:
    result = await db.execute(
        select(UserScope)
        .where(col(UserScope.user_id) == user_id)
        .order_by(col(UserScope.created_at))
    )
    return list(result.scalars())


async def _active_framework(db: AsyncSession) -> uuid.UUID:
    found = (
        await db.execute(
            text(
                "SELECT id FROM geography.geographic_frameworks "
                "WHERE is_active AND deleted_at IS NULL"
            )
        )
    ).scalar_one_or_none()
    if found is None:
        raise BadRequestError("No hay un marco geográfico activo; importa la geografía primero.")
    framework_id: uuid.UUID = found
    return framework_id


def _node_sections_sql(level: ScopeLevel) -> str:
    _, link = _LEVEL_TABLES[level]
    if level is ScopeLevel.ELECTORAL_REGION:
        return (
            "SELECT s.id FROM geography.sections s JOIN geography.states st ON st.id = s.state_id "
            "WHERE st.electoral_region_id = :node AND s.is_active"
        )
    return f"SELECT s.id FROM geography.sections s WHERE s.{link} = :node AND s.is_active"


async def _validate_node(
    db: AsyncSession, level: ScopeLevel, node_id: uuid.UUID, framework_id: uuid.UUID
) -> None:
    table, _ = _LEVEL_TABLES[level]
    found = (
        await db.execute(
            text(
                f"SELECT 1 FROM geography.{table} "
                "WHERE id = :node AND framework_id = :fw AND is_active"
            ),
            {"node": node_id, "fw": framework_id},
        )
    ).first()
    if found is None:
        raise BadRequestError(f"El nodo {node_id} no existe en el marco activo ({level.value}).")


async def rebuild_scope_sections(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Recomputes `user_scope_sections` from `user_scopes` (caller commits)."""
    await db.execute(delete(UserScopeSection).where(col(UserScopeSection.user_id) == user_id))
    scopes = await scopes_of(db, user_id)
    if any(scope.scope_level == ScopeLevel.NATIONAL for scope in scopes):
        return 0  # national: unrestricted, nothing to materialize
    total = 0
    for scope in scopes:
        level = ScopeLevel(scope.scope_level)
        node = getattr(scope, SCOPE_COLUMNS[level])
        sql = _node_sections_sql(level)
        result = await db.execute(
            text(
                "INSERT INTO identity.user_scope_sections (user_id, section_id) "
                f"SELECT :user, id FROM ({sql}) sections ON CONFLICT DO NOTHING"
            ),
            {"user": user_id, "node": node},
        )
        total += result.rowcount  # type: ignore[attr-defined]
    return total


async def ensure_within_scope(db: AsyncSession, actor: GeoScope, *, user_id: uuid.UUID) -> None:
    """The target's scope must be inside the actor's (users without scope are manageable)."""
    if actor.unrestricted:
        return
    target = await resolve_scope(db, user_id, await load_access(db, user_id))
    if target.unrestricted:
        raise ForbiddenError("El usuario tiene un alcance más amplio que el tuyo.")
    outside = (
        await db.execute(
            text(
                "SELECT 1 FROM identity.user_scope_sections t WHERE t.user_id = :target "
                "AND NOT EXISTS (SELECT 1 FROM identity.user_scope_sections a "
                "WHERE a.user_id = :actor AND a.section_id = t.section_id) LIMIT 1"
            ),
            {"target": user_id, "actor": actor.user_id},
        )
    ).first()
    if outside is not None:
        raise ForbiddenError("El usuario está fuera de tu alcance geográfico.")


def manageable_users_filter(
    actor: GeoScope, user_id_column: SectionColumn
) -> ColumnElement[bool] | None:
    """SQL filter: users whose scope is inside the actor's (or who have no scope yet)."""
    if actor.unrestricted:
        return None
    return text(
        "NOT EXISTS (SELECT 1 FROM identity.user_scopes n WHERE n.user_id = users.id "
        "AND n.scope_level = 'national') "
        "AND NOT EXISTS (SELECT 1 FROM identity.user_scope_sections t WHERE t.user_id = users.id "
        "AND NOT EXISTS (SELECT 1 FROM identity.user_scope_sections a "
        "WHERE a.user_id = :scope_actor AND a.section_id = t.section_id))"
    ).bindparams(scope_actor=actor.user_id)  # type: ignore[return-value]


async def set_scopes(
    db: AsyncSession,
    *,
    actor: GeoScope,
    user_id: uuid.UUID,
    scopes: list[tuple[ScopeLevel, uuid.UUID | None]],
) -> list[UserScope]:
    """Replaces the user's scopes (caller commits)."""
    if await repo.user_by_id(db, user_id) is None:
        raise NotFoundError("Usuario no encontrado.")
    framework_id = await _active_framework(db)
    for level, node in scopes:
        if level == ScopeLevel.NATIONAL:
            if node is not None:
                raise BadRequestError("El alcance nacional no lleva nodo.")
            if not actor.unrestricted:
                raise ForbiddenError("Solo un usuario con alcance nacional puede otorgarlo.")
            continue
        if node is None:
            raise BadRequestError(f"El alcance {level.value} requiere un nodo.")
        await _validate_node(db, level, node, framework_id)
        if not actor.unrestricted:
            sql = _node_sections_sql(level)
            outside = (
                await db.execute(
                    text(
                        f"SELECT 1 FROM ({sql}) n WHERE NOT EXISTS (SELECT 1 FROM "
                        "identity.user_scope_sections a WHERE a.user_id = :actor "
                        "AND a.section_id = n.id) LIMIT 1"
                    ),
                    {"node": node, "actor": actor.user_id},
                )
            ).first()
            if outside is not None:
                raise ForbiddenError("No puedes otorgar un alcance fuera del tuyo.")

    # ORM deletes (not a Core DELETE) so the removed scopes stay in the audit log (D-45).
    for previous in await scopes_of(db, user_id):
        await db.delete(previous)
    await db.flush()
    created: list[UserScope] = []
    for level, node in dict.fromkeys(scopes):
        values: dict[str, object] = {"user_id": user_id, "scope_level": level}
        if node is not None:
            values[SCOPE_COLUMNS[level]] = node
        scope = UserScope(**values)  # type: ignore[arg-type]
        db.add(scope)
        created.append(scope)
    await db.flush()
    await rebuild_scope_sections(db, user_id)
    return created


async def rebuild_all(db: AsyncSession) -> int:
    """After activating a framework (scopes already remapped)."""
    users = (await db.execute(select(col(UserScope.user_id)).distinct())).scalars().all()
    for user_id in users:
        await rebuild_scope_sections(db, user_id)
    return len(users)
