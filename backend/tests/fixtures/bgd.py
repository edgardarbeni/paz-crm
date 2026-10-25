"""Synthetic BGD state for tests: real shapefiles written with pyogrio (UTM 13N), plus INE
catalogs. Deterministic, tiny and offline, so CI never needs INE data (D-20).

Layout (meters from X0, Y0), state 01 "ESTADO DE PRUEBA" in circunscripción 2:

    y=2000 +------+------+------+------+     sections 105..108 (top row, DF 2)
           | 105  | 106  | 107  | 108  |
    y=1000 +------+------+------+------+     sections 101..104 (bottom row, DF 1)
           | 101  | 102  | 103  | 104  |
    y=0    +------+------+------+------+
           x=0   1000   2000   3000   4000
           municipio 1 (x<2000) | municipio 2 (x>=2000)
           DL 1 (x<3000)                | DL 2

Edge cases: an invalid (bow-tie) block, a block pointing to a missing section, a block drawn
outside its section, a block with mismatched districts, "SIN NOMBRE" names, a CP needing a
leading zero, a colonia without geometry, CP1252 files without .cpg.
"""

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyogrio.raw
import xlwt

X0, Y0 = 700_000.0, 2_400_000.0
SRID = "EPSG:32613"
STATE = 1
FOLDER_NAME = "01 ESTADO DE PRUEBA"


def _ring(x1: float, y1: float, x2: float, y2: float) -> list[tuple[float, float]]:
    return [
        (X0 + x1, Y0 + y1),
        (X0 + x2, Y0 + y1),
        (X0 + x2, Y0 + y2),
        (X0 + x1, Y0 + y2),
        (X0 + x1, Y0 + y1),
    ]


def polygon(*rings: list[tuple[float, float]]) -> bytes:
    data = struct.pack("<BII", 1, 3, len(rings))
    for ring in rings:
        data += struct.pack("<I", len(ring)) + b"".join(struct.pack("<dd", *p) for p in ring)
    return data


def box(x1: float, y1: float, x2: float, y2: float) -> bytes:
    return polygon(_ring(x1, y1, x2, y2))


def point(x: float, y: float) -> bytes:
    return struct.pack("<BIdd", 1, 1, X0 + x, Y0 + y)


def bowtie(x: float, y: float, size: float) -> bytes:
    """Self-intersecting polygon (invalid); ST_MakeValid repairs it."""
    pts = [(x, y), (x + size, y + size), (x + size, y), (x, y + size), (x, y)]
    return polygon([(X0 + a, Y0 + b) for a, b in pts])


@dataclass
class Layer:
    name: str
    geometry_type: str
    fields: list[tuple[str, str]]  # (name, numpy dtype or "object")
    rows: list[tuple[bytes | None, list[Any]]]
    cpg: bool = False  # keep the .cpg (UTF-8 limit layers) or drop it (CP1252 layers)


def _write(folder: Path, layer: Layer) -> None:
    path = folder / f"{layer.name}.shp"
    geometry = np.array([row[0] for row in layer.rows], dtype=object)
    columns = []
    for index, (_, dtype) in enumerate(layer.fields):
        values = [row[1][index] for row in layer.rows]
        columns.append(np.array(values, dtype=object if dtype == "object" else dtype))
    pyogrio.raw.write(
        path,
        geometry,
        columns,
        [name for name, _ in layer.fields],
        geometry_type=layer.geometry_type,
        crs=SRID,
        encoding="UTF-8" if layer.cpg else "cp1252",
    )
    if not layer.cpg:
        path.with_suffix(".cpg").unlink(missing_ok=True)


def section_number(col: int, row: int) -> int:
    return 101 + col + 4 * row


def sections() -> list[tuple[int, int, int, int, int]]:
    """(number, col, row, municipality, local_district)"""
    return [
        (section_number(c, r), c, r, 1 if c < 2 else 2, 1 if c < 3 else 2)
        for r in range(2)
        for c in range(4)
    ]


def build_state(
    root: Path,
    *,
    municipality_names: tuple[str, str] = ("MUNICIPIO UNO", "MUNICIPIO DOS"),
    drop_section: int | None = None,
    extra_colonia: bool = False,
    without: tuple[str, ...] = (),
) -> Path:
    folder = root / FOLDER_NAME
    folder.mkdir(parents=True, exist_ok=True)
    i32, i64 = "int32", "int64"
    layers = [
        Layer(
            "ENTIDAD",
            "Polygon",
            [
                ("id", i64),
                ("entidad", i64),
                ("nombre", "object"),
                ("circunscri", i64),
                ("crc", i64),
            ],
            [(box(0, 0, 4000, 2000), [1, STATE, "ESTADO DE PRUEBA", 2, 0])],
            cpg=True,
        ),
        Layer(
            "MUNICIPIO",
            "Polygon",
            [("id", i64), ("entidad", i64), ("municipio", i64), ("nombre", "object")],
            [
                (box(0, 0, 2000, 2000), [1, STATE, 1, municipality_names[0]]),
                (box(2000, 0, 4000, 2000), [2, STATE, 2, municipality_names[1]]),
            ],
            cpg=True,
        ),
        Layer(
            "DISTRITO_FEDERAL",
            "Polygon",
            [("id", i64), ("entidad", i64), ("tipo", i64), ("distrito_f", i64)],
            [
                (box(0, 0, 4000, 1000), [1, STATE, 6, 1]),
                (box(0, 1000, 4000, 2000), [2, STATE, 6, 2]),
            ],
            cpg=True,
        ),
        Layer(
            "DISTRITO_LOCAL",
            "Polygon",
            [("id", i64), ("entidad", i64), ("distrito_l", i64)],
            [(box(0, 0, 3000, 2000), [1, STATE, 1]), (box(3000, 0, 4000, 2000), [2, STATE, 2])],
            cpg=True,
        ),
        Layer(
            "SECCION",
            "Polygon",
            [
                ("id", i64),
                ("entidad", i64),
                ("distrito_f", i64),
                ("distrito_l", i64),
                ("municipio", i64),
                ("seccion", i64),
                ("tipo", i64),
            ],
            [
                (
                    box(c * 1000, r * 1000, (c + 1) * 1000, (r + 1) * 1000),
                    [n, STATE, r + 1, dl, mu, n, 2 if c < 2 else 4],
                )
                for n, c, r, mu, dl in sections()
                if n != drop_section
            ],
            cpg=True,
        ),
        # Urban locality 1 (polygon only) over sections 101/102; locality 3 polygon-only in M2.
        Layer(
            "LIMITE_LOCALIDAD",
            "Polygon",
            [
                ("ID", i64),
                ("ENTIDAD", i32),
                ("MUNICIPIO", i32),
                ("LOCALIDAD", i32),
                ("NOMBRE", "object"),
                ("TIPO", i32),
                ("CABECERA", i32),
            ],
            [
                (box(100, 100, 1900, 900), [1, STATE, 1, 1, "VILLA DE PEÑA", 2, 4]),
                (box(2100, 1100, 2400, 1400), [2, STATE, 2, 3, "SIN NOMBRE", 2, 0]),
            ],
        ),
        # Rural locality 2 spans sections 103 and 104 (one point each).
        Layer(
            "LOCALIDAD",
            "Point",
            [
                ("ID", i64),
                ("ENTIDAD", i32),
                ("MUNICIPIO", i32),
                ("SECCION", i32),
                ("LOCALIDAD", i32),
                ("NOMBRE", "object"),
                ("CABECERA", i32),
                ("STATUS", i32),
                ("TIPO", i32),
            ],
            [
                (point(2500, 500), [1, STATE, 2, 103, 2, "RANCHO EL ÁLAMO", 4, 1, 4]),
                (point(3500, 500), [2, STATE, 2, 104, 2, "RANCHO EL ÁLAMO", 4, 1, 4]),
            ],
        ),
        Layer(
            "MANZANA",
            "Polygon",
            [
                ("ID", i64),
                ("ENTIDAD", i32),
                ("MUNICIPIO", i32),
                ("SECCION", i32),
                ("LOCALIDAD", i32),
                ("MANZANA", i32),
                ("STATUS", i32),
                ("DISPERSO", "object"),
                ("Caso_Captu", i64),
                ("DISTRITO_L", i32),
                ("DISTRITO_F", i32),
            ],
            [
                (box(200, 200, 400, 400), [1, STATE, 1, 101, 1, 1, 1, None, 0, 1, 1]),
                (box(500, 200, 700, 400), [2, STATE, 1, 101, 1, 2, 1, "0", 0, 1, 1]),
                (box(1200, 200, 1400, 400), [3, STATE, 1, 102, 1, 1, 2, None, 3, 1, 1]),
                (bowtie(1500, 500, 200), [4, STATE, 1, 102, 1, 2, 1, None, 0, 1, 1]),
                # declared in 101 but drawn inside 102 → outside_section warning
                (box(1600, 200, 1800, 400), [5, STATE, 1, 101, 1, 3, 1, None, 0, 1, 1]),
                # declares DF 2 while section 101 is DF 1 → district_mismatch warning
                (box(200, 600, 400, 800), [6, STATE, 1, 101, 1, 4, 1, None, 0, 1, 2]),
                # section 999 does not exist → missing_parent error
                (box(800, 600, 900, 700), [7, STATE, 1, 999, 1, 1, 1, None, 0, 1, 1]),
            ],
        ),
        Layer(
            "COLONIA",
            "Polygon",
            [
                ("ID", i64),
                ("ENTIDAD", i32),
                ("MUNICIPIO", i32),
                ("NOMBRE", "object"),
                ("CLASIFICAC", i32),
                ("CP", i64),
                ("OTROS_CP", "object"),
            ],
            [
                (box(100, 100, 1900, 900), [10, STATE, 1, "CENTRO", 1, 1000, "0"]),
                (
                    box(2050, 50, 2950, 950),
                    [11, STATE, 2, "FRACC. LAS CAÑADAS", 2, 20906, "20907, 20910"],
                ),
                (None, [12, STATE, 2, "SIN NOMBRE", 1, 0, None]),
            ]
            + (
                [(box(3100, 1100, 3900, 1900), [13, STATE, 2, "NUEVA", 2, 20920, None])]
                if extra_colonia
                else []
            ),
        ),
        Layer(
            "COLONIA_PUNTUAL",
            "Point",
            [
                ("ID", i64),
                ("ENTIDAD", i32),
                ("MUNICIPIO", i32),
                ("NOMBRE", "object"),
                ("CLASIFICAC", i32),
                ("CP", i64),
                ("OTROS_CP", "object"),
            ],
            [(point(3500, 1500), [10, STATE, 2, "LA LOMA", 35, 20930, None])],
        ),
    ]
    for layer in layers:
        if layer.name not in without:
            _write(folder, layer)
    return folder


def build_catalogs(folder: Path) -> Path:
    """INE catalogs for the synthetic state (state folder layout of `paz geo download`)."""
    catalogs = folder / "catalogos"
    catalogs.mkdir(parents=True, exist_ok=True)
    lines = ["ENTIDAD|NOMBRE ENTIDAD|DISTRITO|MUNICIPIO|NOMBRE MUNICIPIO|SECCION|TIPO"]
    for number, col, row, municipality, _ in sections():
        kind = "URBANO(A)" if col < 2 else "RURAL"
        lines.append(f"1|ESTADO DE PRUEBA|{row + 1}|{municipality}|M|{number}|{kind}")
    (catalogs / "secciones.txt").write_text("\n".join(lines) + "\n", encoding="latin-1")
    (catalogs / "localidades_seccion.txt").write_text(
        "ENTIDAD|NOMBRE ENTIDAD|MUNICIPIO|NOMBRE MUNICIPIO|SECCION|LOCALIDAD|NOMBRE LOCALIDAD|TIPO\n"
        "1|ESTADO DE PRUEBA|1|M|101|1|VILLA DE PEÑA|URBANO(A)\n"
        "1|ESTADO DE PRUEBA|2|M|103|2|RANCHO EL ÁLAMO|RURAL\n",
        encoding="latin-1",
    )
    book = xlwt.Workbook()
    sheet = book.add_sheet("Colonias")
    header = [
        "",
        "ID",
        "ENTIDAD",
        "DISTRITO",
        "MUNICIPIO",
        "NOMBRE DEL MUNICIPIO",
        "SECCION",
        "TIPO DE SECCION",
        "TIPO DE COLONIA",
        "NOMBRE DE LA COLONIA",
        "CP",
        "CONTROL",
    ]
    sheet.write(0, 2, "CATALOGO DE COLONIAS")
    for index, value in enumerate(header):
        sheet.write(2, index, value)
    rows = [
        (10, 101, "COLONIA", "CENTRO", 1000),
        (10, 102, "COLONIA", "CENTRO", 1000),
        (11, 103, "FRACCIONAMIENTO", "FRACC. LAS CAÑADAS", 20906),
        (11, 108, "FRACCIONAMIENTO", "FRACC. LAS CAÑADAS", 20906),  # does not touch 108
    ]
    for offset, (colonia, section, kind, name, cp) in enumerate(rows, start=3):
        values: list[object] = [
            "",
            colonia,
            1,
            1,
            1,
            "M",
            section,
            "URBANO(A)",
            kind,
            name,
            cp,
            colonia,
        ]
        for index, cell in enumerate(values):
            sheet.write(offset, index, cell)
    book.save(str(catalogs / "colonias.xls"))
    return folder
