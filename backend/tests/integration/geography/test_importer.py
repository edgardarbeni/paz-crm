"""BGD importer (D-02, D-18, D-57): counts, validation issues, idempotency, reloads, dry run."""

from pathlib import Path

import py7zr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.geography.models import ImportStatus
from tests.fixtures.bgd import build_state
from tests.integration.geography.conftest import Importer, rows, scalar


def _issues(report_issues: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for issue in report_issues:
        key = f"{issue['layer']}:{issue['code']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


async def _run_issues(engine: AsyncEngine, run_id: object) -> dict[str, int]:
    return _issues(
        await rows(
            engine,
            "SELECT layer, code FROM geography.import_issues WHERE import_run_id = :id",
            id=run_id,
        )
    )


async def test_full_import_counts_and_issues(
    run_import: Importer, owner_engine: AsyncEngine
) -> None:
    report = await run_import()
    assert report.status is ImportStatus.SUCCEEDED
    tables = report.counts["tables"]
    expected = {
        "states": 1,
        "municipalities": 2,
        "federal_districts": 2,
        "local_districts": 2,
        "sections": 8,
        "localities": 3,  # 2 polygons + 1 point-only rural locality
        "locality_sections": 2,
        "blocks": 6,  # 7 records, one with a missing section
        "neighborhoods": 4,  # 3 polygons (one without geometry) + 1 point
    }
    assert {name: tables[name]["inserted"] for name in expected} == expected

    issues = await _run_issues(owner_engine, report.run_id)
    assert issues == {
        "MANZANA:geometry_repaired": 1,
        "MANZANA:missing_parent": 1,
        "MANZANA:district_mismatch": 1,
        "MANZANA:outside_section": 1,
        # the layer had an error, so nothing is marked inactive in it (safety net)
        "MANZANA:deactivation_skipped": 1,
        "COLONIA:missing_geometry": 1,
        "COLONIA:catalog_pair_without_overlap": 1,
    }
    assert report.errors == 1
    assert report.warnings == 6

    colonias = {
        row["source_key"]: row
        for row in await rows(
            owner_engine,
            "SELECT source_key, name, postal_code, other_postal_codes, representation, "
            "geom IS NULL AS no_geom FROM geography.neighborhoods",
        )
    }
    assert colonias["10"]["postal_code"] == "01000"
    assert colonias["10"]["other_postal_codes"] == []
    assert colonias["11"]["other_postal_codes"] == ["20907", "20910"]
    assert colonias["12"]["name"] is None  # "SIN NOMBRE" → NULL
    assert colonias["12"]["no_geom"] is True
    assert colonias["P10"]["representation"] == "point"
    names = await rows(owner_engine, "SELECT name FROM geography.localities ORDER BY locality_code")
    assert [row["name"] for row in names] == ["VILLA DE PEÑA", "RANCHO EL ÁLAMO", None]

    # Geometry is in WGS 84 and the repaired bow-tie is valid.
    srids = await scalar(
        owner_engine, "SELECT array_agg(DISTINCT ST_SRID(geom)) FROM geography.blocks"
    )
    assert srids == [4326]
    assert await scalar(owner_engine, "SELECT bool_and(ST_IsValid(geom)) FROM geography.blocks")


async def test_derived_data(run_import: Importer, owner_engine: AsyncEngine) -> None:
    report = await run_import()
    derived = report.counts["derived"]
    assert derived["neighborhood_sections_ine_catalog"] == 4
    assert derived["neighborhood_sections_computed"] == 1  # the point colonia, not in the catalog
    assert derived["section_parts"] >= 8

    pairs = await rows(
        owner_engine,
        "SELECT n.source_key, s.section_number, ns.source, ns.overlap_ratio FROM geography.neighborhood_sections ns "
        "JOIN geography.neighborhoods n ON n.id = ns.neighborhood_id JOIN geography.sections s ON s.id = ns.section_id "
        "ORDER BY 1, 2",
    )
    assert [(p["source_key"], p["section_number"], p["source"]) for p in pairs] == [
        ("10", 101, "ine_catalog"),
        ("10", 102, "ine_catalog"),
        ("11", 103, "ine_catalog"),
        ("11", 108, "ine_catalog"),
        ("P10", 108, "computed"),
    ]
    by_key = {(p["source_key"], p["section_number"]): p["overlap_ratio"] for p in pairs}
    assert float(by_key[("10", 101)]) == float(by_key[("10", 102)])  # symmetric halves
    assert float(by_key[("11", 108)]) == 0  # reported as catalog_pair_without_overlap

    descriptions = await rows(
        owner_engine,
        "SELECT 'section' AS cat, code, description FROM geography.section_types "
        "UNION ALL SELECT 'locality', code, description FROM geography.locality_types "
        "UNION ALL SELECT 'neighborhood', code, description FROM geography.neighborhood_types ORDER BY 1, 2",
    )
    described = {(d["cat"], d["code"]): d["description"] for d in descriptions}
    assert described[("section", 2)] == "URBANO(A)"
    assert described[("section", 4)] == "RURAL"
    assert described[("locality", 2)] == "URBANO(A)"
    assert described[("locality", 4)] == "RURAL"
    assert described[("neighborhood", 1)] == "COLONIA"
    assert described[("neighborhood", 35)] is None  # point colonia type: no catalog evidence

    region = await scalar(
        owner_engine,
        "SELECT ST_Equals(r.geom, s.geom) FROM geography.electoral_regions r "
        "JOIN geography.states s ON s.electoral_region_id = r.id",
    )
    assert region is True


async def test_reimport_is_idempotent_and_keeps_ids(
    run_import: Importer, owner_engine: AsyncEngine
) -> None:
    await run_import()
    ids_before = await scalar(
        owner_engine, "SELECT string_agg(id::text, ',' ORDER BY id) FROM geography.sections"
    )
    blocks_before = await scalar(
        owner_engine, "SELECT string_agg(id::text, ',' ORDER BY id) FROM geography.blocks"
    )

    second = await run_import()
    for name, counts in second.counts["tables"].items():
        assert (counts["inserted"], counts["updated"], counts["deactivated"]) == (0, 0, 0), name
    assert second.counts["tables"]["sections"]["unchanged"] == 8
    assert ids_before == await scalar(
        owner_engine, "SELECT string_agg(id::text, ',' ORDER BY id) FROM geography.sections"
    )
    assert blocks_before == await scalar(
        owner_engine, "SELECT string_agg(id::text, ',' ORDER BY id) FROM geography.blocks"
    )


async def test_reload_with_changes_updates_and_deactivates(
    run_import: Importer, owner_engine: AsyncEngine
) -> None:
    await run_import()
    section_108 = await scalar(
        owner_engine, "SELECT id FROM geography.sections WHERE section_number = 108"
    )

    changed = await run_import(
        municipality_names=("MUNICIPIO UNO RENOMBRADO", "MUNICIPIO DOS"),
        drop_section=108,
        extra_colonia=True,
    )
    tables = changed.counts["tables"]
    assert (tables["municipalities"]["updated"], tables["municipalities"]["unchanged"]) == (1, 1)
    assert tables["sections"]["deactivated"] == 1
    assert tables["neighborhoods"]["inserted"] == 1
    row = (
        await rows(
            owner_engine, "SELECT id, is_active FROM geography.sections WHERE section_number = 108"
        )
    )[0]
    assert (row["id"], row["is_active"]) == (section_108, False)  # same id, kept as history
    assert await scalar(
        owner_engine, "SELECT name FROM geography.municipalities WHERE municipality_code = 1"
    ) == ("MUNICIPIO UNO RENOMBRADO")


async def test_dry_run_writes_nothing_but_the_run(
    run_import: Importer, owner_engine: AsyncEngine
) -> None:
    report = await run_import(dry_run=True)
    assert report.status is ImportStatus.SUCCEEDED
    assert report.counts["tables"]["sections"]["inserted"] == 8
    assert await scalar(owner_engine, "SELECT count(*) FROM geography.sections") == 0
    run = (
        await rows(owner_engine, "SELECT dry_run, status, error_count FROM geography.import_runs")
    )[0]
    assert run == {"dry_run": True, "status": "succeeded", "error_count": 1}
    assert (
        await scalar(
            owner_engine, "SELECT count(*) FROM audit.audit_log WHERE action = 'geo_import'"
        )
        >= 1
    )


async def test_missing_required_layer_fails_cleanly(
    run_import: Importer, owner_engine: AsyncEngine
) -> None:
    report = await run_import(without=("SECCION",))
    assert report.status is ImportStatus.FAILED
    assert "SECCION" in (report.message or "")
    assert await scalar(owner_engine, "SELECT count(*) FROM geography.sections") == 0
    run = (await rows(owner_engine, "SELECT status, message FROM geography.import_runs"))[0]
    assert run["status"] == "failed"


async def test_optional_layers_may_be_missing(
    run_import: Importer, owner_engine: AsyncEngine
) -> None:
    report = await run_import(without=("COLONIA_PUNTUAL", "MANZANA"), catalogs=False)
    assert report.status is ImportStatus.SUCCEEDED
    assert set(report.layers_missing) == {"COLONIA_PUNTUAL", "MANZANA"}
    assert await scalar(owner_engine, "SELECT count(*) FROM geography.blocks") == 0
    assert report.counts["derived"]["neighborhood_sections_computed"] >= 2  # no catalog: computed


async def test_7z_source(run_import: Importer, tmp_path: Path) -> None:
    folder = build_state(tmp_path / "zip")
    archive = tmp_path / "01 ESTADO DE PRUEBA.7z"
    with py7zr.SevenZipFile(archive, "w") as handle:
        handle.writeall(folder, arcname=folder.name)
    report = await run_import(source=archive, catalogs=False)
    assert report.status is ImportStatus.SUCCEEDED
    assert report.counts["tables"]["sections"]["inserted"] == 8


async def test_first_framework_becomes_active(
    run_import: Importer, owner_engine: AsyncEngine
) -> None:
    await run_import(framework="Marco A")
    await run_import(framework="Marco B")
    frameworks = await rows(
        owner_engine, "SELECT name, is_active FROM geography.geographic_frameworks ORDER BY name"
    )
    assert frameworks == [
        {"name": "Marco A", "is_active": True},
        {"name": "Marco B", "is_active": False},
    ]
    # Same natural keys live side by side in different frameworks.
    assert await scalar(owner_engine, "SELECT count(*) FROM geography.sections") == 16


async def test_colonia_type_label_comes_from_the_catalog(
    run_import: Importer, owner_engine: AsyncEngine
) -> None:
    report = await run_import()
    assert report.counts["derived"]["neighborhood_type_labels_updated"] == 2
    labels = await rows(
        owner_engine,
        "SELECT source_key, type_label FROM geography.neighborhoods ORDER BY source_key",
    )
    assert {row["source_key"]: row["type_label"] for row in labels} == {
        "10": "COLONIA",
        "11": "FRACCIONAMIENTO",
        "12": None,
        "P10": None,
    }


async def test_conflicting_code_descriptions_are_cleared_for_good(
    run_import: Importer, owner_engine: AsyncEngine
) -> None:
    """D-62: a code described differently by another state ends up empty and flagged."""
    async with owner_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO geography.neighborhood_types (code, description, description_source) "
                "VALUES (1, 'BARRIO', 'otro estado')"
            )
        )
    report = await run_import()
    assert report.counts["derived"]["code_conflicts"] == 1
    row = (
        await rows(
            owner_engine,
            "SELECT description, description_conflict, description_source FROM geography.neighborhood_types WHERE code = 1",
        )
    )[0]
    assert row["description"] is None
    assert row["description_conflict"] is True
    assert "COLONIA" in row["description_source"]
    issues = await _run_issues(owner_engine, report.run_id)
    assert issues["neighborhood_types:ambiguous_code"] == 1

    again = await run_import()
    assert (
        await scalar(
            owner_engine, "SELECT description FROM geography.neighborhood_types WHERE code = 1"
        )
        is None
    )
    assert again.counts["derived"]["code_conflicts"] == 0  # already flagged: nothing new
    # Unambiguous codes are still described.
    assert (
        await scalar(
            owner_engine, "SELECT description FROM geography.neighborhood_types WHERE code = 2"
        )
        == "FRACCIONAMIENTO"
    )
