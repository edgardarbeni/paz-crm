"""Geographic scope for candidacies (D-34, D-101): a nomination is *readable* when it shares at
least one section with the user's scope and *editable* only when all its sections are in scope."""

import uuid

from sqlalchemy import ColumnElement, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError
from app.modules.candidacies.models import GeographicLevel
from app.modules.identity.services.scopes import GeoScope

# Sections of a geographic node (used before a nomination exists).
_NODE_SECTIONS: dict[GeographicLevel, str] = {
    GeographicLevel.MUNICIPALITY: "SELECT id FROM geography.sections WHERE municipality_id = "
    ":node AND is_active",
    GeographicLevel.LOCAL_DISTRICT: "SELECT id FROM geography.sections WHERE local_district_id = "
    ":node AND is_active",
    GeographicLevel.FEDERAL_DISTRICT: "SELECT id FROM geography.sections WHERE "
    "federal_district_id = :node AND is_active",
    GeographicLevel.STATE: "SELECT id FROM geography.sections WHERE state_id = :node AND is_active",
    GeographicLevel.ELECTORAL_REGION: (
        "SELECT s.id FROM geography.sections s JOIN geography.states st ON st.id = s.state_id "
        "WHERE st.electoral_region_id = :node AND s.is_active"
    ),
    GeographicLevel.NATIONAL: "SELECT id FROM geography.sections WHERE framework_id = :node AND "
    "is_active",
}


def readable_filter(geo: GeoScope) -> ColumnElement[bool] | None:
    if geo.unrestricted:
        return None
    return text(
        "EXISTS (SELECT 1 FROM candidacies.nomination_sections ns "  # noqa: S608 - only scope SQL is interpolated
        "WHERE ns.nomination_id = candidacies.nominations.id AND "
        f"{geo.section_sql('ns.section_id')})"
    ).bindparams(**geo.sql_params)  # type: ignore[return-value]


async def is_editable(db: AsyncSession, geo: GeoScope, nomination_id: uuid.UUID) -> bool:
    """National nominations are editable only with national scope (as for creating them)."""
    if geo.unrestricted:
        return True
    outside = (
        await db.execute(
            text(
                "SELECT 1 FROM candidacies.nominations WHERE id = :n "  # noqa: S608 - only scope SQL is interpolated
                "AND geographic_level = 'national' "
                "UNION ALL "
                "(SELECT 1 FROM candidacies.nomination_sections ns WHERE ns.nomination_id = :n "
                f"AND NOT {geo.section_sql('ns.section_id')} LIMIT 1)"
            ),
            {"n": nomination_id, **geo.sql_params},
        )
    ).first()
    return outside is None


async def is_readable(db: AsyncSession, geo: GeoScope, nomination_id: uuid.UUID) -> bool:
    if geo.unrestricted:
        return True
    inside = (
        await db.execute(
            text(
                "SELECT 1 FROM candidacies.nomination_sections ns "  # noqa: S608
                f"WHERE ns.nomination_id = :n AND {geo.section_sql('ns.section_id')} LIMIT 1"
            ),
            {"n": nomination_id, **geo.sql_params},
        )
    ).first()
    return inside is not None


async def ensure_editable(db: AsyncSession, geo: GeoScope, nomination_id: uuid.UUID) -> None:
    if not await is_editable(db, geo, nomination_id):
        raise ForbiddenError(
            "Solo puedes consultar esta postulación: su geografía excede tu alcance."
        )


async def ensure_node_within_scope(
    db: AsyncSession, geo: GeoScope, level: GeographicLevel, node: uuid.UUID
) -> None:
    if geo.unrestricted:
        return
    if level is GeographicLevel.NATIONAL:
        raise ForbiddenError(
            "Solo un usuario con alcance nacional puede crear postulaciones nacionales."
        )
    outside = (
        await db.execute(
            text(
                f"SELECT 1 FROM ({_NODE_SECTIONS[level]}) n "  # noqa: S608
                f"WHERE NOT {geo.section_sql('n.id')} LIMIT 1"
            ),
            {"node": node, **geo.sql_params},
        )
    ).first()
    if outside is not None:
        raise ForbiddenError("No puedes crear una postulación fuera de tu alcance geográfico.")
