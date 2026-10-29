"""Staging → final tables, set-based SQL (D-02, D-18).

- Every BGD layer gets a temporary staging table (empty if the layer is missing) filled with
  COPY; geometries are reprojected to EPSG:4326 and repaired once, in staging.
- Final tables are upserted by natural key: IDs never change, unchanged rows are not written,
  and rows absent from the source are marked `is_active = false`.
"""

import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import Settings
from app.modules.geography.generalize import generalize
from app.modules.geography.importer.catalogs import IneCatalogs
from app.modules.geography.importer.layers import LOAD_ORDER, SPECS, Issue, Staged

_UUID_BINDS = re.compile(r"(?<![:\w]):(fw|run|state)\b")
_POLYGON = "ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_Transform(ST_MakeValid(ST_GeomFromWKB(wkb, {srid})), 4326)), 3))"
_POINT = "ST_Transform(ST_GeomFromWKB(wkb, {srid}), 4326)"


@dataclass
class TableCounts:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    deactivated: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "deactivated": self.deactivated,
        }


@dataclass
class LoadResult:
    counts: dict[str, TableCounts] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    derived: dict[str, int] = field(default_factory=dict)


class Loader:
    def __init__(
        self,
        connection: AsyncConnection,
        settings: Settings,
        *,
        framework_id: uuid.UUID,
        run_id: uuid.UUID,
        state_code: int,
    ) -> None:
        self.connection = connection
        self.settings = settings
        self.framework_id = framework_id
        self.run_id = run_id
        self.state_code = state_code
        self.state_id: uuid.UUID | None = None
        self.result = LoadResult()
        self._layer_errors: Counter[str] = Counter()

    # --- helpers ---------------------------------------------------------------------------

    async def _exec(self, sql: str, **params: Any) -> Any:
        # asyncpg cannot infer the type of a bind used in a SELECT list: cast the uuid binds.
        sql = _UUID_BINDS.sub(r"CAST(:\1 AS uuid)", sql)
        return await self.connection.execute(text(sql), params)

    def _params(self) -> dict[str, Any]:
        return {"fw": self.framework_id, "run": self.run_id, "state": self.state_id}

    def issue(self, issue: Issue) -> None:
        self.result.issues.append(issue)
        if issue.severity == "error":
            self._layer_errors[issue.layer] += 1

    # --- staging -----------------------------------------------------------------------------

    async def stage(self, staged: dict[str, Staged], srid: int) -> None:
        raw = await self.connection.get_raw_connection()
        driver = raw.driver_connection
        assert driver is not None  # noqa: S101
        for name in LOAD_ORDER:
            spec = SPECS[name]
            layer = staged.get(name)
            for item in layer.issues if layer else []:
                self.issue(item)
            columns = ", ".join(f"{c.name} {c.kind.value}" for c in spec.columns)
            await self._exec(
                f"CREATE TEMP TABLE {spec.table} (fid integer, {columns}, wkb bytea) ON COMMIT DROP"
            )
            if layer and layer.rows:
                await driver.copy_records_to_table(
                    spec.table, records=layer.rows, columns=layer.column_names
                )
            await self._prepare_geometry(name, srid)

    async def _prepare_geometry(self, name: str, srid: int) -> None:
        spec = SPECS[name]
        table = spec.table
        expression = (_POLYGON if spec.geometry == "polygon" else _POINT).format(srid=int(srid))
        invalid = await self._exec(
            f"SELECT fid FROM {table} WHERE wkb IS NOT NULL "
            f"AND NOT ST_IsValid(ST_GeomFromWKB(wkb, {int(srid)}))"
        )
        for (fid,) in invalid.all():
            self.issue(
                Issue(
                    name,
                    "warning",
                    "geometry_repaired",
                    "Geometría inválida reparada (ST_MakeValid).",
                    fid,
                )
            )
        await self._exec(f"ALTER TABLE {table} ADD COLUMN geom geometry")
        await self._exec(f"UPDATE {table} SET geom = {expression} WHERE wkb IS NOT NULL")
        if spec.geometry_required:
            empty = await self._exec(
                f"DELETE FROM {table} WHERE geom IS NULL OR ST_IsEmpty(geom) RETURNING fid"
            )
            for (fid,) in empty.all():
                self.issue(
                    Issue(
                        name,
                        "error",
                        "empty_geometry",
                        "La geometría quedó vacía tras repararla.",
                        fid,
                    )
                )
        await self._exec(f"ANALYZE {table}")

    # --- upserts -----------------------------------------------------------------------------

    async def _upsert(
        self,
        table: str,
        *,
        insert_columns: list[str],
        select_sql: str,
        conflict: list[str],
        compare: list[str],
        source_rows: int,
    ) -> TableCounts:
        assignments = ", ".join(f"{column} = EXCLUDED.{column}" for column in compare)
        current = ", ".join(f"t.{column}" for column in compare)
        incoming = ", ".join(f"EXCLUDED.{column}" for column in compare)
        sql = f"""
            WITH upserted AS (
              INSERT INTO geography.{table} AS t ({", ".join(insert_columns)}, import_run_id, is_active)
              SELECT source.*, :run, true FROM ({select_sql}) AS source
              ON CONFLICT ({", ".join(conflict)}) DO UPDATE SET
                {assignments}, import_run_id = EXCLUDED.import_run_id, is_active = true,
                updated_at = now()
              WHERE ROW({current}, t.is_active) IS DISTINCT FROM ROW({incoming}, true)
              RETURNING old.id IS NULL AS inserted  -- PG18: OLD is NULL for inserts
            )
            SELECT count(*) FILTER (WHERE inserted), count(*) FILTER (WHERE NOT inserted)
            FROM upserted
        """
        inserted, updated = (await self._exec(sql, **self._params())).one()
        counts = TableCounts(inserted=int(inserted), updated=int(updated))
        counts.unchanged = max(source_rows - counts.inserted - counts.updated, 0)
        self.result.counts[table] = counts
        return counts

    async def _count(self, table: str) -> int:
        return int((await self._exec(f"SELECT count(*) FROM {table}")).scalar_one())

    async def _missing_parent(
        self, layer: str, sql: str, message: str, key_columns: list[str]
    ) -> None:
        rows = await self._exec(sql, **self._params())
        for row in rows.mappings():
            key = {column: row[column] for column in key_columns}
            self.issue(Issue(layer, "error", "missing_parent", message, row["fid"], key))

    async def _deactivate(self, layer: str, table: str, sql: str) -> None:
        """Marks rows absent from the source inactive — only if the layer loaded cleanly, so a
        broken file can never deactivate valid data."""
        if self._layer_errors[layer]:
            self.issue(
                Issue(
                    layer,
                    "warning",
                    "deactivation_skipped",
                    "La capa tuvo errores; no se marcaron registros como inactivos.",
                )
            )
            return
        result = await self._exec(sql, **self._params())
        self.result.counts.setdefault(table, TableCounts()).deactivated = result.rowcount

    async def _codes(self, catalog: str, select_sql: str) -> None:
        await self._exec(
            f"INSERT INTO geography.{catalog} (code) {select_sql} ON CONFLICT (code) DO NOTHING"
        )

    # --- entities ----------------------------------------------------------------------------

    async def load_states(self) -> None:
        rows = await self._count("stg_entidad")
        if rows != 1:
            raise ValueError(f"ENTIDAD debe tener exactamente un registro válido (tiene {rows}).")
        await self._exec(
            "INSERT INTO geography.electoral_regions (framework_id, region_number, import_run_id) "
            "SELECT DISTINCT :fw, region_number, :run FROM stg_entidad "
            "ON CONFLICT (framework_id, region_number) DO NOTHING",
            fw=self.framework_id,
            run=self.run_id,
        )
        await self._upsert(
            "states",
            insert_columns=[
                "framework_id",
                "electoral_region_id",
                "state_code",
                "name",
                "source_id",
                "geom",
            ],
            select_sql="""
                SELECT :fw, r.id, s.state_code, s.name, s.source_id, s.geom FROM stg_entidad s
                JOIN geography.electoral_regions r
                  ON r.framework_id = :fw AND r.region_number = s.region_number
            """,
            conflict=["framework_id", "state_code"],
            compare=["electoral_region_id", "name", "source_id", "geom"],
            source_rows=rows,
        )
        self.state_id = (
            await self._exec(
                "SELECT id FROM geography.states WHERE framework_id = :fw AND state_code = :code",
                fw=self.framework_id,
                code=self.state_code,
            )
        ).scalar_one()

    async def load_municipalities(self) -> None:
        await self._upsert(
            "municipalities",
            insert_columns=[
                "framework_id",
                "state_id",
                "municipality_code",
                "name",
                "source_id",
                "geom",
            ],
            select_sql="SELECT :fw, :state, municipality_code, name, source_id, geom FROM stg_municipio",
            conflict=["state_id", "municipality_code"],
            compare=["name", "source_id", "geom"],
            source_rows=await self._count("stg_municipio"),
        )
        await self._deactivate(
            "MUNICIPIO",
            "municipalities",
            "UPDATE geography.municipalities SET is_active = false, updated_at = now() "
            "WHERE state_id = :state AND is_active AND municipality_code NOT IN "
            "(SELECT municipality_code FROM stg_municipio)",
        )

    async def load_districts(self) -> None:
        await self._codes(
            "federal_district_types",
            "SELECT DISTINCT district_type_code FROM stg_distrito_federal WHERE district_type_code IS NOT NULL",
        )
        for layer, table, extra in (
            ("DISTRITO_FEDERAL", "federal_districts", ["district_type_code"]),
            ("DISTRITO_LOCAL", "local_districts", []),
        ):
            staging = SPECS[layer].table
            columns = ["district_number", *extra, "source_id", "geom"]
            await self._upsert(
                table,
                insert_columns=["framework_id", "state_id", *columns],
                select_sql=f"SELECT :fw, :state, {', '.join(columns)} FROM {staging}",
                conflict=["state_id", "district_number"],
                compare=[*extra, "source_id", "geom"],
                source_rows=await self._count(staging),
            )
            await self._deactivate(
                layer,
                table,
                f"UPDATE geography.{table} SET is_active = false, updated_at = now() "
                f"WHERE state_id = :state AND is_active AND district_number NOT IN "
                f"(SELECT district_number FROM {staging})",
            )

    async def load_sections(self) -> None:
        await self._codes(
            "section_types",
            "SELECT DISTINCT section_type_code FROM stg_seccion WHERE section_type_code IS NOT NULL",
        )
        joins = """
            FROM stg_seccion s
            LEFT JOIN geography.municipalities mu
              ON mu.state_id = :state AND mu.municipality_code = s.municipality_code
            LEFT JOIN geography.federal_districts fd
              ON fd.state_id = :state AND fd.district_number = s.federal_district
            LEFT JOIN geography.local_districts ld
              ON ld.state_id = :state AND ld.district_number = s.local_district
        """
        await self._missing_parent(
            "SECCION",
            f"SELECT s.fid, s.section_number {joins} WHERE mu.id IS NULL OR fd.id IS NULL OR ld.id IS NULL",
            "Municipio o distrito inexistente para la sección.",
            ["section_number"],
        )
        await self._upsert(
            "sections",
            insert_columns=[
                "framework_id",
                "state_id",
                "section_number",
                "municipality_id",
                "federal_district_id",
                "local_district_id",
                "section_type_code",
                "source_id",
                "geom",
            ],
            select_sql=f"""
                SELECT :fw, :state, s.section_number, mu.id, fd.id, ld.id, s.section_type_code,
                       s.source_id, s.geom
                {joins} WHERE mu.id IS NOT NULL AND fd.id IS NOT NULL AND ld.id IS NOT NULL
            """,
            conflict=["state_id", "section_number"],
            compare=[
                "municipality_id",
                "federal_district_id",
                "local_district_id",
                "section_type_code",
                "source_id",
                "geom",
            ],
            source_rows=await self._count("stg_seccion"),
        )
        await self._deactivate(
            "SECCION",
            "sections",
            "UPDATE geography.sections SET is_active = false, updated_at = now() "
            "WHERE state_id = :state AND is_active AND section_number NOT IN "
            "(SELECT section_number FROM stg_seccion)",
        )

    async def load_localities(self) -> None:
        for catalog, column in (
            ("locality_types", "locality_type_code"),
            ("locality_head_types", "head_type_code"),
        ):
            await self._codes(
                catalog,
                f"SELECT {column} FROM stg_limite_localidad WHERE {column} IS NOT NULL "
                f"UNION SELECT {column} FROM stg_localidad WHERE {column} IS NOT NULL",
            )
        picked = """
            WITH candidates AS (
              SELECT fid, municipality_code, locality_code, name, locality_type_code,
                     head_type_code, geom, 1 AS priority
              FROM stg_limite_localidad
              UNION ALL
              SELECT fid, municipality_code, locality_code, name, locality_type_code,
                     head_type_code, NULL::geometry, 2
              FROM stg_localidad
            ), picked AS (
              SELECT DISTINCT ON (municipality_code, locality_code) *
              FROM candidates
              ORDER BY municipality_code, locality_code, priority, name NULLS LAST
            )
        """
        await self._missing_parent(
            "LOCALIDAD",
            picked
            + """
                SELECT p.fid, p.municipality_code, p.locality_code FROM picked p
                LEFT JOIN geography.municipalities mu
                  ON mu.state_id = :state AND mu.municipality_code = p.municipality_code
                WHERE mu.id IS NULL
            """,
            "Municipio inexistente para la localidad.",
            ["municipality_code", "locality_code"],
        )
        source_rows = int(
            (
                await self._exec(
                    "SELECT count(*) FROM (SELECT municipality_code, locality_code FROM stg_limite_localidad "
                    "UNION SELECT municipality_code, locality_code FROM stg_localidad) k"
                )
            ).scalar_one()
        )
        await self._upsert(
            "localities",
            insert_columns=[
                "framework_id",
                "state_id",
                "municipality_id",
                "locality_code",
                "name",
                "locality_type_code",
                "head_type_code",
                "geom",
            ],
            select_sql=picked
            + """
                SELECT :fw, :state, mu.id, p.locality_code, p.name, p.locality_type_code,
                       p.head_type_code, p.geom
                FROM picked p
                JOIN geography.municipalities mu
                  ON mu.state_id = :state AND mu.municipality_code = p.municipality_code
            """,
            conflict=["municipality_id", "locality_code"],
            compare=["name", "locality_type_code", "head_type_code", "geom"],
            source_rows=source_rows,
        )
        if self._layer_errors["LIMITE_LOCALIDAD"] == 0:
            await self._deactivate(
                "LOCALIDAD",
                "localities",
                """
                UPDATE geography.localities l SET is_active = false, updated_at = now()
                FROM geography.municipalities mu
                WHERE l.state_id = :state AND l.is_active AND mu.id = l.municipality_id
                  AND (mu.municipality_code, l.locality_code) NOT IN (
                    SELECT municipality_code, locality_code FROM stg_limite_localidad
                    UNION SELECT municipality_code, locality_code FROM stg_localidad)
                """,
            )

        joins = """
            FROM stg_localidad p
            LEFT JOIN geography.municipalities mu
              ON mu.state_id = :state AND mu.municipality_code = p.municipality_code
            LEFT JOIN geography.localities l
              ON l.municipality_id = mu.id AND l.locality_code = p.locality_code
            LEFT JOIN geography.sections s
              ON s.state_id = :state AND s.section_number = p.section_number
        """
        await self._missing_parent(
            "LOCALIDAD",
            f"SELECT p.fid, p.locality_code, p.section_number {joins} WHERE l.id IS NULL OR s.id IS NULL",
            "Localidad o sección inexistente para el punto de localidad.",
            ["locality_code", "section_number"],
        )
        await self._upsert(
            "locality_sections",
            insert_columns=[
                "framework_id",
                "locality_id",
                "section_id",
                "name",
                "status_code",
                "head_type_code",
                "source_id",
                "geom",
            ],
            select_sql=f"""
                SELECT :fw, l.id, s.id, p.name, p.status_code, p.head_type_code, p.source_id, p.geom
                {joins} WHERE l.id IS NOT NULL AND s.id IS NOT NULL
            """,
            conflict=["locality_id", "section_id"],
            compare=["name", "status_code", "head_type_code", "source_id", "geom"],
            source_rows=await self._count("stg_localidad"),
        )
        await self._deactivate(
            "LOCALIDAD",
            "locality_sections",
            """
            UPDATE geography.locality_sections ls SET is_active = false, updated_at = now()
            FROM geography.localities l, geography.sections s, geography.municipalities mu
            WHERE ls.locality_id = l.id AND ls.section_id = s.id AND mu.id = l.municipality_id
              AND l.state_id = :state AND ls.is_active
              AND (mu.municipality_code, l.locality_code, s.section_number) NOT IN (
                SELECT municipality_code, locality_code, section_number FROM stg_localidad)
            """,
        )

    async def load_blocks(self) -> None:
        await self._codes(
            "block_statuses",
            "SELECT DISTINCT status_code FROM stg_manzana WHERE status_code IS NOT NULL",
        )
        joins = """
            FROM stg_manzana b
            LEFT JOIN geography.sections s
              ON s.state_id = :state AND s.section_number = b.section_number
            LEFT JOIN geography.municipalities mu
              ON mu.state_id = :state AND mu.municipality_code = b.municipality_code
            LEFT JOIN geography.localities l
              ON l.municipality_id = mu.id AND l.locality_code = b.locality_code
        """
        await self._missing_parent(
            "MANZANA",
            f"SELECT b.fid, b.section_number, b.locality_code, b.block_number {joins} "
            "WHERE s.id IS NULL OR l.id IS NULL",
            "Sección o localidad inexistente para la manzana.",
            ["section_number", "locality_code", "block_number"],
        )
        await self._upsert(
            "blocks",
            insert_columns=[
                "framework_id",
                "section_id",
                "locality_id",
                "block_number",
                "status_code",
                "dispersed_raw",
                "capture_case",
                "source_id",
                "geom",
            ],
            select_sql=f"""
                SELECT :fw, s.id, l.id, b.block_number, b.status_code, b.dispersed_raw,
                       b.capture_case, b.source_id, b.geom
                {joins} WHERE s.id IS NOT NULL AND l.id IS NOT NULL
            """,
            conflict=["framework_id", "section_id", "locality_id", "block_number"],
            compare=["status_code", "dispersed_raw", "capture_case", "source_id", "geom"],
            source_rows=await self._count("stg_manzana"),
        )
        await self._deactivate(
            "MANZANA",
            "blocks",
            """
            UPDATE geography.blocks b SET is_active = false, updated_at = now()
            FROM geography.sections s, geography.localities l
            WHERE b.framework_id = :fw AND b.section_id = s.id AND b.locality_id = l.id
              AND s.state_id = :state AND b.is_active
              AND (s.section_number, l.locality_code, b.block_number) NOT IN (
                SELECT section_number, locality_code, block_number FROM stg_manzana)
            """,
        )
        # Districts written on the block must match its section's (D-20): warnings only.
        mismatches = await self._exec(
            """
            SELECT b.fid, b.section_number, b.block_number, b.federal_district, b.local_district,
                   fd.district_number AS section_fd, ld.district_number AS section_ld
            FROM stg_manzana b
            JOIN geography.sections s ON s.state_id = :state AND s.section_number = b.section_number
            JOIN geography.federal_districts fd ON fd.id = s.federal_district_id
            JOIN geography.local_districts ld ON ld.id = s.local_district_id
            WHERE (b.federal_district IS NOT NULL AND b.federal_district <> fd.district_number)
               OR (b.local_district IS NOT NULL AND b.local_district <> ld.district_number)
            """,
            **self._params(),
        )
        for row in mismatches.mappings():
            self.issue(
                Issue(
                    "MANZANA",
                    "warning",
                    "district_mismatch",
                    f"La manzana declara DF {row['federal_district']}/DL {row['local_district']}; "
                    f"su sección es DF {row['section_fd']}/DL {row['section_ld']}. Manda la sección.",
                    row["fid"],
                    {"section_number": row["section_number"], "block_number": row["block_number"]},
                )
            )

    async def load_neighborhoods(self) -> None:
        await self._codes(
            "neighborhood_types",
            "SELECT neighborhood_type_code FROM stg_colonia WHERE neighborhood_type_code IS NOT NULL "
            "UNION SELECT neighborhood_type_code FROM stg_colonia_puntual "
            "WHERE neighborhood_type_code IS NOT NULL",
        )
        candidates = """
            WITH candidates AS (
              SELECT fid, source_key, municipality_code, name, neighborhood_type_code, postal_code,
                     other_postal_codes, 'polygon' AS representation, geom
              FROM stg_colonia
              UNION ALL
              SELECT fid, source_key, municipality_code, name, neighborhood_type_code, postal_code,
                     other_postal_codes, 'point', geom
              FROM stg_colonia_puntual
            )
        """
        await self._missing_parent(
            "COLONIA",
            candidates
            + """
                SELECT c.fid, c.source_key FROM candidates c
                LEFT JOIN geography.municipalities mu
                  ON mu.state_id = :state AND mu.municipality_code = c.municipality_code
                WHERE mu.id IS NULL
            """,
            "Municipio inexistente para la colonia.",
            ["source_key"],
        )
        source_rows = await self._count("stg_colonia") + await self._count("stg_colonia_puntual")
        await self._upsert(
            "neighborhoods",
            insert_columns=[
                "framework_id",
                "state_id",
                "municipality_id",
                "source_key",
                "name",
                "neighborhood_type_code",
                "postal_code",
                "other_postal_codes",
                "representation",
                "geom",
            ],
            select_sql=candidates
            + """
                SELECT :fw, :state, mu.id, c.source_key, c.name, c.neighborhood_type_code,
                       c.postal_code, COALESCE(c.other_postal_codes, '{}'), c.representation, c.geom
                FROM candidates c
                JOIN geography.municipalities mu
                  ON mu.state_id = :state AND mu.municipality_code = c.municipality_code
            """,
            conflict=["state_id", "source_key"],
            compare=[
                "municipality_id",
                "name",
                "neighborhood_type_code",
                "postal_code",
                "other_postal_codes",
                "representation",
                "geom",
            ],
            source_rows=source_rows,
        )
        if self._layer_errors["COLONIA_PUNTUAL"] == 0:
            await self._deactivate(
                "COLONIA",
                "neighborhoods",
                "UPDATE geography.neighborhoods SET is_active = false, updated_at = now() "
                "WHERE state_id = :state AND is_active AND source_key NOT IN "
                "(SELECT source_key FROM stg_colonia UNION SELECT source_key FROM stg_colonia_puntual)",
            )

    # --- derived data --------------------------------------------------------------------------

    async def derive(self, catalogs: IneCatalogs, staged: dict[str, Staged]) -> None:
        await self._electoral_regions()
        await self._generalized_geometries()
        await self._section_parts()
        await self._blocks_outside_sections()
        await self._neighborhood_sections(catalogs)
        await self._code_descriptions(catalogs, staged)
        await self._neighborhood_type_labels(catalogs)

    async def _electoral_regions(self) -> None:
        result = await self._exec(
            """
            UPDATE geography.electoral_regions r SET geom = agg.geom, updated_at = now()
            FROM (
              SELECT electoral_region_id, ST_Multi(ST_Union(geom)) AS geom
              FROM geography.states WHERE framework_id = :fw AND is_active
              GROUP BY electoral_region_id
            ) agg
            WHERE r.id = agg.electoral_region_id AND r.geom IS DISTINCT FROM agg.geom
            """,
            **self._params(),
        )
        self.result.derived["electoral_regions_geometry_updated"] = result.rowcount

    async def _generalized_geometries(self) -> None:
        """Simplified copies for low-zoom tiles (D-80); unchanged rows are not rewritten."""
        if self.state_id is None:  # the state did not load: nothing to generalize
            return
        self.result.derived["generalized_geometries"] = await generalize(
            self.connection, framework_id=self.framework_id, state_id=self.state_id
        )

    async def _section_parts(self) -> None:
        await self._exec(
            "DELETE FROM geography.section_parts sp USING geography.sections s "
            "WHERE sp.section_id = s.id AND s.state_id = :state",
            **self._params(),
        )
        result = await self._exec(
            f"""
            INSERT INTO geography.section_parts (section_id, geom)
            SELECT id, part FROM (
              SELECT id, ST_Subdivide(geom, {int(self.settings.geo_section_subdivide_vertices)}) AS part
              FROM geography.sections WHERE state_id = :state AND is_active
            ) parts
            WHERE GeometryType(part) = 'POLYGON'
            """,
            **self._params(),
        )
        self.result.derived["section_parts"] = result.rowcount

    async def _blocks_outside_sections(self) -> None:
        rows = await self._exec(
            """
            SELECT b.source_id, s.section_number, b.block_number
            FROM geography.blocks b JOIN geography.sections s ON s.id = b.section_id
            WHERE b.framework_id = :fw AND s.state_id = :state AND b.is_active
              AND NOT ST_Intersects(s.geom, ST_PointOnSurface(b.geom))
            """,
            **self._params(),
        )
        for row in rows.mappings():
            self.issue(
                Issue(
                    "MANZANA",
                    "warning",
                    "outside_section",
                    "La manzana cae geométricamente fuera de su sección declarada.",
                    None,
                    {
                        "section_number": row["section_number"],
                        "block_number": row["block_number"],
                        "source_id": row["source_id"],
                    },
                )
            )

    async def _neighborhood_sections(self, catalogs: IneCatalogs) -> None:
        await self._exec(
            "CREATE TEMP TABLE stg_colonia_seccion (source_key text, section_number integer) "
            "ON COMMIT DROP"
        )
        if catalogs.neighborhood_sections:
            raw = await self.connection.get_raw_connection()
            assert raw.driver_connection is not None  # noqa: S101
            await raw.driver_connection.copy_records_to_table(
                "stg_colonia_seccion",
                records=sorted(catalogs.neighborhood_sections),
                columns=["source_key", "section_number"],
            )
        await self._exec(
            "DELETE FROM geography.neighborhood_sections ns USING geography.neighborhoods n "
            "WHERE ns.neighborhood_id = n.id AND n.state_id = :state",
            **self._params(),
        )
        overlap = """
            CASE WHEN n.representation = 'polygon' AND n.geom IS NOT NULL THEN
              LEAST(1, ST_Area(ST_Intersection(n.geom, s.geom)::geography)
                       / NULLIF(ST_Area(n.geom::geography), 0)) END
        """
        area = """
            CASE WHEN n.representation = 'polygon' AND n.geom IS NOT NULL THEN
              ST_Area(ST_Intersection(n.geom, s.geom)::geography) END
        """
        catalog = await self._exec(
            f"""
            INSERT INTO geography.neighborhood_sections
              (neighborhood_id, section_id, source, overlap_ratio, overlap_area_m2)
            SELECT n.id, s.id, 'ine_catalog', {overlap}, {area}
            FROM stg_colonia_seccion c
            JOIN geography.neighborhoods n ON n.state_id = :state AND n.source_key = c.source_key
            JOIN geography.sections s ON s.state_id = :state AND s.section_number = c.section_number
            WHERE n.is_active AND s.is_active
            ON CONFLICT DO NOTHING
            """,
            **self._params(),
        )
        computed = await self._exec(
            f"""
            INSERT INTO geography.neighborhood_sections
              (neighborhood_id, section_id, source, overlap_ratio, overlap_area_m2)
            SELECT neighborhood_id, section_id, 'computed', ratio, area FROM (
              SELECT n.id AS neighborhood_id, s.id AS section_id, {overlap} AS ratio, {area} AS area,
                     n.representation
              FROM geography.neighborhoods n
              JOIN geography.sections s
                ON s.state_id = :state AND s.is_active AND ST_Intersects(n.geom, s.geom)
              WHERE n.state_id = :state AND n.is_active AND n.geom IS NOT NULL
                AND NOT EXISTS (
                  SELECT 1 FROM geography.neighborhood_sections x WHERE x.neighborhood_id = n.id)
            ) candidates
            WHERE representation = 'point'
               OR ratio >= CAST(:min_ratio AS double precision)
               OR area >= CAST(:min_area AS double precision)
            """,
            **self._params(),
            min_ratio=self.settings.geo_neighborhood_min_ratio,
            min_area=self.settings.geo_neighborhood_min_area_m2,
        )
        self.result.derived["neighborhood_sections_ine_catalog"] = catalog.rowcount
        self.result.derived["neighborhood_sections_computed"] = computed.rowcount

        if catalogs.neighborhood_sections:
            no_overlap = await self._exec(
                """
                SELECT n.source_key, s.section_number FROM geography.neighborhood_sections ns
                JOIN geography.neighborhoods n ON n.id = ns.neighborhood_id
                JOIN geography.sections s ON s.id = ns.section_id
                WHERE n.state_id = :state AND ns.source = 'ine_catalog'
                  AND n.representation = 'polygon' AND n.geom IS NOT NULL
                  AND COALESCE(ns.overlap_area_m2, 0) = 0
                """,
                **self._params(),
            )
            for row in no_overlap.mappings():
                self.issue(
                    Issue(
                        "COLONIA",
                        "warning",
                        "catalog_pair_without_overlap",
                        "El catálogo del INE relaciona la colonia con una sección que no toca.",
                        None,
                        dict(row),
                    )
                )
            unknown = await self._exec(
                """
                SELECT c.source_key, c.section_number FROM stg_colonia_seccion c
                LEFT JOIN geography.neighborhoods n ON n.state_id = :state AND n.source_key = c.source_key
                LEFT JOIN geography.sections s ON s.state_id = :state AND s.section_number = c.section_number
                WHERE n.id IS NULL OR s.id IS NULL
                """,
                **self._params(),
            )
            for row in unknown.mappings():
                self.issue(
                    Issue(
                        "COLONIA",
                        "warning",
                        "catalog_pair_unknown",
                        "El catálogo del INE menciona una colonia o sección que no está en la BGD.",
                        None,
                        dict(row),
                    )
                )

    async def _code_descriptions(self, catalogs: IneCatalogs, staged: dict[str, Staged]) -> None:
        """Learns code → text from the INE catalogs by joining them with the BGD records (D-15).

        A description is accepted only while all evidence agrees, nationally (D-62): if this
        state's records disagree among themselves, or with what another state established,
        the code is flagged `description_conflict`, its description is cleared and it is never
        filled automatically again."""
        mappings: dict[str, dict[int, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))

        def rows(layer: str) -> list[dict[str, Any]]:
            item = staged.get(layer)
            if item is None:
                return []
            names = item.column_names
            return [dict(zip(names, row, strict=True)) for row in item.rows]

        for row in rows("SECCION"):
            label = catalogs.section_types.get(row["section_number"])
            if label and row["section_type_code"] is not None:
                mappings["section_types"][row["section_type_code"]][label] += 1
        for layer in ("LOCALIDAD", "LIMITE_LOCALIDAD"):
            for row in rows(layer):
                label = catalogs.locality_types.get(
                    (row["municipality_code"], row["locality_code"])
                )
                if label and row["locality_type_code"] is not None:
                    mappings["locality_types"][row["locality_type_code"]][label] += 1
        for row in rows("COLONIA"):
            label = catalogs.neighborhood_types.get(row["source_key"])
            if label and row["neighborhood_type_code"] is not None:
                mappings["neighborhood_types"][row["neighborhood_type_code"]][label] += 1

        described = conflicts = 0
        for catalog, by_code in mappings.items():
            for code, labels in by_code.items():
                if len(labels) == 1:
                    (label,) = labels
                    accepted = await self._exec(
                        f"UPDATE geography.{catalog} SET description = :label, description_source = :source "
                        "WHERE code = :code AND NOT description_conflict AND description IS NULL",
                        label=label,
                        source=catalogs.source_label,
                        code=code,
                    )
                    described += accepted.rowcount
                    clash = await self._exec(
                        f"UPDATE geography.{catalog} SET description = NULL, description_conflict = true, "
                        "description_source = :why WHERE code = :code AND description IS NOT NULL "
                        "AND description <> :label RETURNING code",
                        label=label,
                        code=code,
                        why=f"Conflicto: el estado {self.state_code:02d} indica «{label}»",
                    )
                    if clash.first() is None:
                        continue
                    message = f"El código {code} contradice la descripción de otro estado («{label}» aquí)."
                else:
                    await self._exec(
                        f"UPDATE geography.{catalog} SET description = NULL, description_conflict = true, "
                        "description_source = :why WHERE code = :code",
                        code=code,
                        why=f"Conflicto en el estado {self.state_code:02d}",
                    )
                    message = f"El código {code} corresponde a varios textos: {dict(labels.most_common(5))}."
                conflicts += 1
                self.issue(
                    Issue(catalog, "warning", "ambiguous_code", message + " Queda sin descripción.")
                )
        self.result.derived["code_descriptions_updated"] = described
        self.result.derived["code_conflicts"] = conflicts

    async def _neighborhood_type_labels(self, catalogs: IneCatalogs) -> None:
        """Per-colonia official type text, independent of the (unreliable) code (D-62)."""
        if catalogs.neighborhood_types:
            await self._exec(
                "CREATE TEMP TABLE stg_colonia_tipo (source_key text, label text) ON COMMIT DROP"
            )
            raw = await self.connection.get_raw_connection()
            assert raw.driver_connection is not None  # noqa: S101
            await raw.driver_connection.copy_records_to_table(
                "stg_colonia_tipo",
                records=sorted(catalogs.neighborhood_types.items()),
                columns=["source_key", "label"],
            )
            labelled = await self._exec(
                "UPDATE geography.neighborhoods n SET type_label = t.label, updated_at = now() "
                "FROM stg_colonia_tipo t WHERE n.state_id = :state AND n.source_key = t.source_key "
                "AND n.type_label IS DISTINCT FROM t.label",
                **self._params(),
            )
            self.result.derived["neighborhood_type_labels_updated"] = labelled.rowcount
