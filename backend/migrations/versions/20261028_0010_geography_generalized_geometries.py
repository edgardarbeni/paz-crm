"""geography: generalized geometries for low-zoom vector tiles (D-80)

`geom_low` (served at z <= 6) and `geom_mid` (z 7-9) hold simplified copies of `geom`,
filled by the importer or `paz geo generalize`. Nullable: tiles fall back to `geom` until a
framework is generalized. No index: tiles keep filtering on the GiST index of `geom`.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = {
    "states": ("geom_low", "geom_mid"),
    "federal_districts": ("geom_low", "geom_mid"),
    "local_districts": ("geom_low", "geom_mid"),
    "municipalities": ("geom_low", "geom_mid"),
    "sections": ("geom_mid",),
}


def _geometry() -> geoalchemy2.types.Geometry:
    return geoalchemy2.types.Geometry(
        geometry_type="MULTIPOLYGON",
        srid=4326,
        dimension=2,
        spatial_index=False,
        from_text="ST_GeomFromEWKT",
        name="geometry",
    )


def upgrade() -> None:
    for table, columns in _COLUMNS.items():
        for column in columns:
            op.add_column(table, sa.Column(column, _geometry(), nullable=True), schema="geography")


def downgrade() -> None:
    for table, columns in _COLUMNS.items():
        for column in columns:
            op.drop_column(table, column, schema="geography")
