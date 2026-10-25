"""INE tabular catalogs (Productos Cartográficos, D-15, D-57, D-59).

Files are expected in one folder per state, with the names written by `paz geo download`:

- ``secciones.txt``            Catálogo de Secciones (pipe separated, Latin-1)
- ``localidades_seccion.txt``  Catálogo de Localidades con Sección
- ``colonias.xls``             Catálogo de Colonias (one row per colonia-sección pair)

Catalogs give the *text* of a code (URBANO(A), RURAL…) but not the code; the importer joins
them with the BGD records to learn the code → text mapping, never guessing a meaning.
"""

from dataclasses import dataclass, field
from pathlib import Path

import xlrd

SECTIONS_FILE = "secciones.txt"
LOCALITIES_FILE = "localidades_seccion.txt"
NEIGHBORHOODS_FILE = "colonias.xls"


@dataclass
class IneCatalogs:
    folder: Path | None
    cutoff: str | None = None
    # section_number → section type text
    section_types: dict[int, str] = field(default_factory=dict)
    # (municipality, locality) → locality type text
    locality_types: dict[tuple[int, int], str] = field(default_factory=dict)
    # colonia ID (BGD) → colonia type text
    neighborhood_types: dict[str, str] = field(default_factory=dict)
    # (colonia ID, section_number) pairs — the official relation (D-57)
    neighborhood_sections: set[tuple[str, int]] = field(default_factory=set)

    @property
    def source_label(self) -> str:
        return f"INE, catálogos de productos cartográficos ({self.cutoff or 'corte no indicado'})"


def _pipe_rows(path: Path) -> list[dict[str, str]]:
    lines = path.read_text(encoding="latin-1").splitlines()
    header = [name.strip().upper() for name in lines[0].split("|")]
    return [
        dict(zip(header, (v.strip() for v in line.split("|")), strict=False))
        for line in lines[1:]
        if line
    ]


def _xls_rows(path: Path) -> list[dict[str, object]]:
    sheet = xlrd.open_workbook(str(path)).sheet_by_index(0)
    header: list[str] | None = None
    rows: list[dict[str, object]] = []
    for index in range(sheet.nrows):
        values = sheet.row_values(index)
        upper = [str(value).strip().upper() for value in values]
        if header is None:
            if "ID" in upper and "SECCION" in upper:
                header = upper
            continue
        if any(str(value).strip() for value in values):
            rows.append(dict(zip(header, values, strict=False)))
    return rows


def _int(value: object) -> int | None:
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return None


def load_catalogs(folder: Path | None, *, cutoff: str | None = None) -> IneCatalogs:
    catalogs = IneCatalogs(folder=folder, cutoff=cutoff)
    if folder is None or not folder.is_dir():
        return catalogs

    sections = folder / SECTIONS_FILE
    if sections.exists():
        for row in _pipe_rows(sections):
            number = _int(row.get("SECCION", ""))
            if number is not None and row.get("TIPO"):
                catalogs.section_types[number] = row["TIPO"]

    localities = folder / LOCALITIES_FILE
    if localities.exists():
        for row in _pipe_rows(localities):
            municipality, locality = _int(row.get("MUNICIPIO", "")), _int(row.get("LOCALIDAD", ""))
            if municipality is not None and locality is not None and row.get("TIPO"):
                catalogs.locality_types[(municipality, locality)] = row["TIPO"]

    neighborhoods = folder / NEIGHBORHOODS_FILE
    if neighborhoods.exists():
        for xls_row in _xls_rows(neighborhoods):
            colonia, section = _int(xls_row.get("ID")), _int(xls_row.get("SECCION"))
            if colonia is None:
                continue
            kind = str(xls_row.get("TIPO DE COLONIA") or "").strip()
            if kind:
                catalogs.neighborhood_types[str(colonia)] = kind
            if section is not None:
                catalogs.neighborhood_sections.add((str(colonia), section))
    return catalogs
