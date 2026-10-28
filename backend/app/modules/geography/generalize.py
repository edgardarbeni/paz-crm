"""Generalized geometries for low-zoom vector tiles (D-80).

Levels seen at low zoom keep simplified copies of `geom`, computed at import time:
`geom_low` is served at z <= 6 and `geom_mid` at z 7-9; from z 10 tiles use `geom`.
The tolerance is GENERALIZE_TOLERANCE_UNITS tile units (4096 extent) at the band's highest
zoom, so the error stays under half a pixel on a 512 px tile.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

GENERALIZE_TOLERANCE_UNITS = 4
# Width of one tile unit at z0 (Web Mercator circumference / 4096), in meters.
_UNIT_M_Z0 = 40_075_016.686 / 4096
_M_PER_DEGREE = 111_320.0


@dataclass(frozen=True)
class Band:
    column: str
    max_zoom: int

    @property
    def tolerance(self) -> float:
        """Simplification tolerance in degrees (geometries are stored in EPSG:4326)."""
        return GENERALIZE_TOLERANCE_UNITS * _UNIT_M_Z0 / 2.0**self.max_zoom / _M_PER_DEGREE


LOW = Band("geom_low", 6)
MID = Band("geom_mid", 9)

# table → bands it stores (neighborhoods and blocks are only tiled at z >= 12 and need none)
GENERALIZED: dict[str, tuple[Band, ...]] = {
    "states": (LOW, MID),
    "federal_districts": (LOW, MID),
    "local_districts": (LOW, MID),
    "municipalities": (LOW, MID),
    "sections": (MID,),
}


def tile_geometry(table: str, z: int) -> str:
    """SQL expression for the geometry to tile from `geography.<table> s` at zoom `z`.

    Falls back to `s.geom` while a framework has not been generalized yet."""
    for band in GENERALIZED.get(table, ()):
        if z <= band.max_zoom:
            return f"COALESCE(s.{band.column}, s.geom)"
    return "s.geom"


async def generalize(
    connection: AsyncConnection, *, framework_id: uuid.UUID, state_id: uuid.UUID | None = None
) -> int:
    """Fill the generalized columns of a framework (or one of its states).

    Rows whose stored value is already current are not written, so a reload without changes
    updates nothing. Returns the number of column values written."""
    written = 0
    for table, bands in GENERALIZED.items():
        where = "framework_id = :fw AND is_active AND geom IS NOT NULL"
        if state_id is not None:
            where += " AND id = :state" if table == "states" else " AND state_id = :state"
        for band in bands:
            result = await connection.execute(
                text(
                    f"""
                    UPDATE geography.{table} t SET {band.column} = g.simplified
                    FROM (
                      SELECT id, ST_Multi(ST_SimplifyPreserveTopology(geom, :tolerance)) AS simplified
                      FROM geography.{table} WHERE {where}
                    ) g
                    WHERE t.id = g.id AND NOT ST_IsEmpty(g.simplified)
                      AND t.{band.column} IS DISTINCT FROM g.simplified
                    """
                ),
                {"fw": framework_id, "state": state_id, "tolerance": band.tolerance},
            )
            written += result.rowcount
    return written
