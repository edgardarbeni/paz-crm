import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.modules.geography.importer.layers import SPECS, postal_code, postal_codes, stage
from app.modules.geography.importer.source import LayerData, SourceError, _clean, open_source
from app.modules.geography.ine import (
    IneClient,
    IneDownloadError,
    Manifest,
    cutoff_of,
    download_state,
)
from app.modules.geography.service import format_key, tile_bounds_ok
from tests.fixtures.bgd import build_state
from tests.support import make_settings


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1000, "01000"), ("20906", "20906"), (0, None), (None, None), ("", None), (1000.0, "01000")],
)
def test_postal_code(value: object, expected: str | None) -> None:
    assert postal_code(value) == expected


def test_postal_codes() -> None:
    assert postal_codes("20907, 20910;20907") == ["20907", "20910"]
    assert postal_codes("0") == []
    assert postal_codes(None) == []


def test_clean_values() -> None:
    assert _clean("  SIN NOMBRE ") is None
    assert _clean("sin   nombre") is None
    assert _clean("  Centro ") == "Centro"
    assert _clean(float("nan")) is None
    assert _clean("") is None


def _layer(name: str, rows: list[dict[str, Any]]) -> LayerData:
    columns = {key: [row.get(key) for row in rows] for key in rows[0]}
    return LayerData(
        name=name, srid=32613, fids=list(range(len(rows))), wkb=[b"x"] * len(rows), columns=columns
    )


def test_stage_validates_records() -> None:
    spec = SPECS["MUNICIPIO"]
    data = _layer(
        "MUNICIPIO",
        [
            {"entidad": 1, "municipio": 1, "nombre": "UNO", "id": 1},
            {"entidad": 1, "municipio": 1, "nombre": "DUP", "id": 2},  # duplicate key
            {"entidad": 2, "municipio": 3, "nombre": "OTRO ESTADO", "id": 3},
            {"entidad": 1, "municipio": None, "nombre": "SIN CLAVE", "id": 4},
            {"entidad": 1, "municipio": 2.5, "nombre": "DECIMAL", "id": 5},
        ],
    )
    staged = stage(spec, data, state_code=1)
    assert len(staged.rows) == 1
    assert [issue.code for issue in staged.issues] == [
        "duplicate_key",
        "invalid_record",
        "invalid_record",
        "invalid_record",
    ]
    missing = stage(spec, _layer("MUNICIPIO", [{"entidad": 1}]), state_code=1)
    assert [issue.code for issue in missing.issues] == ["missing_field"]


def test_open_source_variants(tmp_path: Path) -> None:
    build_state(tmp_path)
    with open_source(tmp_path, state_code=1) as parent:
        assert parent.has("SECCION")
        layer = parent.read("MANZANA")  # CP1252, no .cpg
        assert layer.srid == 32613
        assert "caso_captu" in layer.columns  # names lower-cased
        assert len(parent.sha256(["SECCION", "MANZANA"])) == 64
    with open_source(tmp_path / "01 ESTADO DE PRUEBA", state_code=1) as direct:
        assert direct.has("ENTIDAD")
    with pytest.raises(SourceError, match="estado 02"), open_source(tmp_path, state_code=2):
        pass
    no_state = tmp_path / "otro"
    (no_state / "readme").mkdir(parents=True)
    with (
        pytest.raises(SourceError, match="carpeta del estado 01"),
        open_source(no_state, state_code=1),
    ):
        pass
    empty_state = tmp_path / "vacio" / "01 VACIO"
    empty_state.mkdir(parents=True)
    (empty_state / "readme.txt").write_text("x")
    with (
        pytest.raises(SourceError, match="no contiene shapefiles"),
        open_source(empty_state.parent, state_code=1),
    ):
        pass
    with (
        pytest.raises(SourceError, match="No existe"),
        open_source(tmp_path / "nope", state_code=1),
    ):
        pass


def test_format_keys() -> None:
    row = {"code": 338}
    assert format_key("section", 1, row) == "01-0338"
    assert format_key("municipality", 9, {"code": 5}) == "09-005"
    assert format_key("federal_district", 9, {"code": 12}) == "09-12"
    assert format_key("state", None, {"code": 9}) == "09"
    assert format_key("electoral_region", None, {"code": 2}) == "C2"
    assert format_key("locality", 1, {"code": 1, "municipality_code": 3}) == "01-003-0001"
    assert format_key("neighborhood", 1, {"code": "1265"}) == "01-COL-1265"
    assert tile_bounds_ok(0, 0, 0)
    assert not tile_bounds_ok(2, 4, 0)
    assert not tile_bounds_ok(23, 0, 0)


def test_cutoff_parsing() -> None:
    assert cutoff_of("CORTE_19ENE2026_PRODUCTOSCARTOGRAFICOS/CATALOGOS/") == "19ENE2026"
    assert cutoff_of("BGD_15_diciembre_2025/") is None


def _ine_transport(*, bgd_items: list[dict[str, str]] | None = None) -> httpx.MockTransport:
    catalog_path = "CORTE_19ENE2026_PRODUCTOSCARTOGRAFICOS/CATALOGOS/ENTIDAD/1/X/"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/api/bases/" in url:
            items = (
                bgd_items
                if bgd_items is not None
                else [{"path": "BGD_15_diciembre_2025/04 SHAPEFILE/", "archivo": "01 AGS.7z"}]
            )
            return httpx.Response(200, json=items)
        if "/api/catalogos" in url:
            product = request.url.params["producto"]
            extension = ".xls" if product == "CCol" else ".txt"
            return httpx.Response(
                200,
                json=[
                    {
                        "path": "CORTE_19ENE2026_PRODUCTOSCARTOGRAFICOS/CATALOGOS/ENTIDAD/10/X/",
                        "archivo": f"f{extension}",
                    },
                    {"path": catalog_path, "archivo": f"Catálogo{extension}"},
                    {"path": catalog_path, "archivo": "Catálogo.mdb"},
                ],
            )
        if url.startswith("https://storage.googleapis.com/mapoteca/"):
            return httpx.Response(200, content=b"contenido-" + request.url.path.encode())
        return httpx.Response(404)

    return httpx.MockTransport(handler)


async def test_download_state_with_mock_ine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = _ine_transport()
    original = httpx.AsyncClient

    def client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr("app.modules.geography.ine.httpx.AsyncClient", client_factory)
    manifest = await download_state(make_settings(), 1, tmp_path)
    assert manifest.catalogs_cutoff == "19ENE2026"
    assert manifest.bgd_cutoff == "BGD_15_diciembre_2025"
    kinds = [item.kind for item in manifest.files]
    assert kinds == ["bgd", "catalog:Csecc", "catalog:CLS", "catalog:CCol"]
    assert (tmp_path / "01" / "catalogos" / "colonias.xls").read_bytes().startswith(b"contenido-")
    assert "%C3%A1" in manifest.files[1].url  # path is URL-encoded (Catálogo)
    loaded = Manifest.load(tmp_path / "01")
    assert loaded is not None
    assert loaded.files[0].sha256 == manifest.files[0].sha256
    assert json.loads((tmp_path / "01" / "manifest.json").read_text())["state_code"] == 1
    assert Manifest.load(tmp_path) is None


async def test_ine_client_errors() -> None:
    async with httpx.AsyncClient(transport=_ine_transport(bgd_items=[])) as http:
        client = IneClient(make_settings(), http)
        with pytest.raises(IneDownloadError, match="BGD"):
            await client.bgd_item(1)
        with pytest.raises(IneDownloadError, match="catálogo"):
            await client.catalog_item("Csecc", 31)
