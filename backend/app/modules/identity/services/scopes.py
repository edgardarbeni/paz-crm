"""Geographic scope (D-34, D-101): what part of the country a user may see and act on.

- Each grant has scope nodes (national, region, state, DF, DL, municipality, section).
- They resolve to sections, materialized per grant in `user_grant_sections` for non-national
  scopes; repositories filter with EXISTS against it (query layer, not only endpoints).
- A request's scope is the one *for the permission it exercises*: the union of the grants whose
  role includes that permission (`GeoScope.grant_ids`). `grants_all` (superadmin) and a national
  grant see everything. No grant = sees nothing (deny by default).
- Modules never read `user_grant_sections` directly: they use `sections_filter` (ORM) or
  `section_sql` + `sql_params` (raw SQL).
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import ColumnElement, delete, exists, false, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped
from sqlmodel import col

from app.core.errors import BadRequestError, ForbiddenError
from app.modules.identity.models import SCOPE_COLUMNS, ScopeLevel, UserGrantScope, UserGrantSection
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

_GRANTS_PARAM = "scope_grants"


@dataclass(frozen=True, slots=True)
class GeoScope:
    """Resolved scope of a user for one permission (or for all their grants)."""

    user_id: uuid.UUID
    unrestricted: bool
    grant_ids: tuple[uuid.UUID, ...] = field(default=())

    def sections_filter(self, section_id: SectionColumn) -> ColumnElement[bool] | None:
        """EXISTS clause limiting `section_id` to the scope's sections (None = no filter)."""
        if self.unrestricted:
            return None
        if not self.grant_ids:
            return false()
        return exists().where(
            col(UserGrantSection.grant_id).in_(self.grant_ids),
            col(UserGrantSection.section_id) == section_id,
        )

    def section_sql(self, section_expr: str, *, alias: str = "u") -> str:
        """Raw-SQL twin of `sections_filter`: `EXISTS (…)` over `section_expr`. Bind
        `sql_params`. Callers skip it when `unrestricted`."""
        return (
            f"EXISTS (SELECT 1 FROM identity.user_grant_sections {alias} "
            f"WHERE {alias}.grant_id = ANY(CAST(:{_GRANTS_PARAM} AS uuid[])) "
            f"AND {alias}.section_id = {section_expr})"
        )

    def sections_join_sql(self, alias: str = "u") -> str:
        """`identity.user_grant_sections <alias>` restricted to the scope, for JOINs (add
        `ON <alias>.section_id = …`). Bind `sql_params`."""
        return (
            f"(SELECT DISTINCT section_id FROM identity.user_grant_sections "
            f"WHERE grant_id = ANY(CAST(:{_GRANTS_PARAM} AS uuid[]))) {alias}"
        )

    @property
    def sql_params(self) -> dict[str, Any]:
        return {_GRANTS_PARAM: list(self.grant_ids)}

    async def contains_section(self, db: AsyncSession, section_id: uuid.UUID | None) -> bool:
        if self.unrestricted:
            return True
        if section_id is None or not self.grant_ids:
            return False
        found = await db.execute(
            select(col(UserGrantSection.section_id)).where(
                col(UserGrantSection.grant_id).in_(self.grant_ids),
                col(UserGrantSection.section_id) == section_id,
            )
        )
        return found.first() is not None

    def covers(self, other: "GeoScope") -> bool:
        """Cheap sufficient test: every grant of `other` is also one of ours (same sections)."""
        return self.unrestricted or set(other.grant_ids) <= set(self.grant_ids)


async def scope_covers(db: AsyncSession, outer: GeoScope, inner: GeoScope) -> bool:
    """True if every section of `inner` is also in `outer`."""
    if outer.covers(inner):
        return True
    if inner.unrestricted:
        return False
    found = (
        await db.execute(
            text(
                "SELECT 1 FROM identity.user_grant_sections t "
                "WHERE t.grant_id = ANY(CAST(:inner AS uuid[])) "
                "AND NOT EXISTS (SELECT 1 FROM identity.user_grant_sections o "
                "WHERE o.grant_id = ANY(CAST(:outer AS uuid[])) AND o.section_id = t.section_id) "
                "LIMIT 1"
            ),
            {"inner": list(inner.grant_ids), "outer": list(outer.grant_ids)},
        )
    ).first()
    return found is None


def geo_for(user_id: uuid.UUID, access: Access, permission: str | None = None) -> GeoScope:
    """The scope `access` has for `permission` (for all its grants when None)."""
    if access.grants_all:
        return GeoScope(user_id=user_id, unrestricted=True)
    grants = access.grants_for(permission)
    return GeoScope(
        user_id=user_id,
        unrestricted=any(grant.national for grant in grants),
        grant_ids=tuple(grant.id for grant in grants),
    )


async def resolve_scope(
    db: AsyncSession, user_id: uuid.UUID, access: Access, permission: str | None = None
) -> GeoScope:
    """Kept async for callers outside a request (jobs, imports)."""
    del db
    return geo_for(user_id, access, permission)


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


async def ensure_node_within(
    db: AsyncSession, actor: GeoScope, level: ScopeLevel, node: uuid.UUID | None
) -> None:
    """A node can only be handed out inside the actor's scope (geographic anti-escalation)."""
    if actor.unrestricted:
        return
    if level == ScopeLevel.NATIONAL:
        raise ForbiddenError(
            "Solo quien tiene alcance nacional para esos permisos puede otorgarlo."
        )
    outside = (
        await db.execute(
            text(
                f"SELECT 1 FROM ({_node_sections_sql(level)}) n "
                f"WHERE NOT {actor.section_sql('n.id', alias='a')} LIMIT 1"
            ),
            {"node": node, **actor.sql_params},
        )
    ).first()
    if outside is not None:
        raise ForbiddenError("No puedes otorgar un alcance fuera del tuyo.")


async def grant_scopes(db: AsyncSession, grant_id: uuid.UUID) -> list[UserGrantScope]:
    result = await db.execute(
        select(UserGrantScope)
        .where(col(UserGrantScope.grant_id) == grant_id)
        .order_by(col(UserGrantScope.created_at), col(UserGrantScope.id))
    )
    return list(result.scalars())


async def rebuild_grant_sections(db: AsyncSession, grant_id: uuid.UUID) -> int:
    """Recomputes `user_grant_sections` from `user_grant_scopes` (caller commits)."""
    await db.execute(delete(UserGrantSection).where(col(UserGrantSection.grant_id) == grant_id))
    scopes = await grant_scopes(db, grant_id)
    if any(scope.scope_level == ScopeLevel.NATIONAL for scope in scopes):
        return 0  # national: unrestricted, nothing to materialize
    total = 0
    for scope in scopes:
        level = ScopeLevel(scope.scope_level)
        node = getattr(scope, SCOPE_COLUMNS[level])
        result = await db.execute(
            text(
                "INSERT INTO identity.user_grant_sections (grant_id, section_id) "
                f"SELECT :grant, id FROM ({_node_sections_sql(level)}) sections "
                "ON CONFLICT DO NOTHING"
            ),
            {"grant": grant_id, "node": node},
        )
        total += result.rowcount  # type: ignore[attr-defined]
    return total


# A user's whole scope (all grants), for "is the target inside the actor?" checks.
_TARGET_NATIONAL = (
    "EXISTS (SELECT 1 FROM identity.user_grants g JOIN identity.roles r ON r.id = g.role_id "
    "WHERE g.user_id = {user} AND (r.grants_all OR EXISTS (SELECT 1 FROM "
    "identity.user_grant_scopes gs WHERE gs.grant_id = g.id AND gs.scope_level = 'national')))"
)
_TARGET_OUTSIDE = (
    "EXISTS (SELECT 1 FROM identity.user_grants g JOIN identity.user_grant_sections t "
    "ON t.grant_id = g.id WHERE g.user_id = {user} AND NOT {inside})"
)


async def ensure_within_scope(db: AsyncSession, actor: GeoScope, *, user_id: uuid.UUID) -> None:
    """The target's scope must be inside the actor's (users without scope are manageable)."""
    if actor.unrestricted:
        return
    target = geo_for(user_id, await load_access(db, user_id))
    if target.unrestricted:
        raise ForbiddenError("El usuario tiene un alcance más amplio que el tuyo.")
    outside = (
        await db.execute(
            text(
                "SELECT "
                + _TARGET_OUTSIDE.format(user=":target", inside=actor.section_sql("t.section_id"))
            ),
            {"target": user_id, **actor.sql_params},
        )
    ).scalar_one()
    if outside:
        raise ForbiddenError("El usuario está fuera de tu alcance geográfico.")


def manageable_users_filter(
    actor: GeoScope, user_id_column: SectionColumn
) -> ColumnElement[bool] | None:
    """SQL filter: users whose scope is inside the actor's (or who have no scope yet)."""
    del user_id_column  # the filter correlates on `identity.users.id`
    if actor.unrestricted:
        return None
    return text(
        "NOT "
        + _TARGET_NATIONAL.format(user="users.id")
        + " AND NOT "
        + _TARGET_OUTSIDE.format(user="users.id", inside=actor.section_sql("t.section_id"))
    ).bindparams(**actor.sql_params)  # type: ignore[return-value]


async def rebuild_all(db: AsyncSession) -> int:
    """After activating a framework (grant scopes already remapped)."""
    grants = (await db.execute(select(col(UserGrantScope.grant_id)).distinct())).scalars().all()
    for grant_id in grants:
        await rebuild_grant_sections(db, grant_id)
    return len(grants)


# Shared with modules that resolve their own geographic zones (e.g. Peace Movement coordinators).
node_sections_sql = _node_sections_sql
validate_node = _validate_node
active_framework = _active_framework
