"""Layer specifications: BGD field → staging column, with per-record validation.

Each valid record becomes a staging row (plus its WKB); each problem becomes an `Issue`.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.modules.geography.importer.source import LayerData


class Kind(StrEnum):
    INT = "integer"
    TEXT = "text"
    TEXT_ARRAY = "text[]"


@dataclass(frozen=True, slots=True)
class Column:
    name: str
    source: str
    kind: Kind = Kind.INT
    required: bool = True
    transform: Callable[[Any], Any] | None = None


@dataclass(frozen=True, slots=True)
class Issue:
    layer: str
    severity: str  # "error" | "warning"
    code: str
    message: str
    source_fid: int | None = None
    natural_key: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class LayerSpec:
    name: str
    columns: tuple[Column, ...]
    geometry: str  # "polygon" | "point"
    required_layer: bool
    geometry_required: bool = True
    key: tuple[str, ...] = ()

    @property
    def table(self) -> str:
        return f"stg_{self.name.lower()}"


@dataclass
class Staged:
    spec: LayerSpec
    srid: int
    rows: list[tuple[Any, ...]] = field(default_factory=list)  # fid, *columns, wkb
    issues: list[Issue] = field(default_factory=list)

    @property
    def column_names(self) -> list[str]:
        return ["fid", *(column.name for column in self.spec.columns), "wkb"]


def postal_code(value: Any) -> str | None:
    """CP as char(5) with leading zeros (CDMX 01000…); 0 or empty → NULL (§3.2)."""
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(int(value)) if isinstance(value, float) else str(value))
    if not digits or int(digits) == 0:
        return None
    return digits.zfill(5)[-5:]


def postal_codes(value: Any) -> list[str]:
    """OTROS_CP → list of CPs; "0" or empty → [] (§3.2)."""
    if value is None:
        return []
    codes = [postal_code(part) for part in re.split(r"[,;/\s]+", str(value))]
    return sorted({code for code in codes if code})


def _int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("boolean")
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{value} no es entero")
        return int(value)
    if isinstance(value, int):
        return value
    text = str(value).strip()
    return int(text) if text else None


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


SPECS: dict[str, LayerSpec] = {
    spec.name: spec
    for spec in (
        LayerSpec(
            "ENTIDAD",
            (
                Column("state_code", "entidad"),
                Column("name", "nombre", Kind.TEXT),
                Column("region_number", "circunscri"),
                Column("source_id", "id", required=False),
            ),
            geometry="polygon",
            required_layer=True,
            key=("state_code",),
        ),
        LayerSpec(
            "MUNICIPIO",
            (
                Column("state_code", "entidad"),
                Column("municipality_code", "municipio"),
                Column("name", "nombre", Kind.TEXT),
                Column("source_id", "id", required=False),
            ),
            geometry="polygon",
            required_layer=True,
            key=("municipality_code",),
        ),
        LayerSpec(
            "DISTRITO_FEDERAL",
            (
                Column("state_code", "entidad"),
                Column("district_number", "distrito_f"),
                Column("district_type_code", "tipo", required=False),
                Column("source_id", "id", required=False),
            ),
            geometry="polygon",
            required_layer=True,
            key=("district_number",),
        ),
        LayerSpec(
            "DISTRITO_LOCAL",
            (
                Column("state_code", "entidad"),
                Column("district_number", "distrito_l"),
                Column("source_id", "id", required=False),
            ),
            geometry="polygon",
            required_layer=True,
            key=("district_number",),
        ),
        LayerSpec(
            "SECCION",
            (
                Column("state_code", "entidad"),
                Column("section_number", "seccion"),
                Column("municipality_code", "municipio"),
                Column("federal_district", "distrito_f"),
                Column("local_district", "distrito_l"),
                Column("section_type_code", "tipo", required=False),
                Column("source_id", "id", required=False),
            ),
            geometry="polygon",
            required_layer=True,
            key=("section_number",),
        ),
        LayerSpec(
            "LIMITE_LOCALIDAD",
            (
                Column("state_code", "entidad"),
                Column("municipality_code", "municipio"),
                Column("locality_code", "localidad"),
                Column("name", "nombre", Kind.TEXT, required=False),
                Column("locality_type_code", "tipo", required=False),
                Column("head_type_code", "cabecera", required=False),
            ),
            geometry="polygon",
            required_layer=False,
            key=("municipality_code", "locality_code"),
        ),
        LayerSpec(
            "LOCALIDAD",
            (
                Column("state_code", "entidad"),
                Column("municipality_code", "municipio"),
                Column("section_number", "seccion"),
                Column("locality_code", "localidad"),
                Column("name", "nombre", Kind.TEXT, required=False),
                Column("locality_type_code", "tipo", required=False),
                Column("head_type_code", "cabecera", required=False),
                Column("status_code", "status", required=False),
                Column("source_id", "id", required=False),
            ),
            geometry="point",
            required_layer=False,
            key=("municipality_code", "locality_code", "section_number"),
        ),
        LayerSpec(
            "MANZANA",
            (
                Column("state_code", "entidad"),
                Column("municipality_code", "municipio"),
                Column("section_number", "seccion"),
                Column("locality_code", "localidad"),
                Column("block_number", "manzana"),
                Column("status_code", "status", required=False),
                Column("dispersed_raw", "disperso", Kind.TEXT, required=False),
                Column("capture_case", "caso_captu", required=False),
                Column("federal_district", "distrito_f", required=False),
                Column("local_district", "distrito_l", required=False),
                Column("source_id", "id", required=False),
            ),
            geometry="polygon",
            required_layer=False,
            key=("section_number", "locality_code", "block_number"),
        ),
        LayerSpec(
            "COLONIA",
            (
                Column("source_key", "id", Kind.TEXT, transform=lambda v: str(_int(v))),
                Column("state_code", "entidad"),
                Column("municipality_code", "municipio"),
                Column("name", "nombre", Kind.TEXT, required=False),
                Column("neighborhood_type_code", "clasificac", required=False),
                Column("postal_code", "cp", Kind.TEXT, required=False, transform=postal_code),
                Column(
                    "other_postal_codes",
                    "otros_cp",
                    Kind.TEXT_ARRAY,
                    required=False,
                    transform=postal_codes,
                ),
            ),
            geometry="polygon",
            required_layer=False,
            geometry_required=False,
            key=("source_key",),
        ),
        LayerSpec(
            "COLONIA_PUNTUAL",
            (
                # Prefixed so point and polygon colonias never collide on the key (D-58).
                Column("source_key", "id", Kind.TEXT, transform=lambda v: f"P{_int(v)}"),
                Column("state_code", "entidad"),
                Column("municipality_code", "municipio"),
                Column("name", "nombre", Kind.TEXT, required=False),
                Column("neighborhood_type_code", "clasificac", required=False),
                Column("postal_code", "cp", Kind.TEXT, required=False, transform=postal_code),
                Column(
                    "other_postal_codes",
                    "otros_cp",
                    Kind.TEXT_ARRAY,
                    required=False,
                    transform=postal_codes,
                ),
            ),
            geometry="point",
            required_layer=False,
            geometry_required=False,
            key=("source_key",),
        ),
    )
}

LOAD_ORDER = (
    "ENTIDAD",
    "MUNICIPIO",
    "DISTRITO_FEDERAL",
    "DISTRITO_LOCAL",
    "SECCION",
    "LIMITE_LOCALIDAD",
    "LOCALIDAD",
    "MANZANA",
    "COLONIA",
    "COLONIA_PUNTUAL",
)


def stage(spec: LayerSpec, data: LayerData, *, state_code: int) -> Staged:  # noqa: PLR0912
    staged = Staged(spec=spec, srid=data.srid)
    available = set(data.columns)
    missing_fields = [c.source for c in spec.columns if c.required and c.source not in available]
    if missing_fields:
        staged.issues.append(
            Issue(
                spec.name, "error", "missing_field", f"Faltan campos: {', '.join(missing_fields)}"
            )
        )
        return staged

    seen: dict[tuple[Any, ...], int] = {}
    for fid, wkb, raw in data.records():
        values: dict[str, Any] = {}
        problems: list[str] = []
        for column in spec.columns:
            value = raw.get(column.source)
            try:
                if column.transform is not None:
                    value = column.transform(value) if value is not None else column.transform(None)
                elif column.kind is Kind.INT:
                    value = _int(value)
                else:
                    value = _text(value)
            except (ValueError, TypeError) as exc:
                problems.append(f"{column.source}: {exc}")
                value = None
            if column.required and value is None:
                problems.append(f"{column.source} vacío")
            values[column.name] = value
        key = {name: values.get(name) for name in spec.key}

        if values.get("state_code") is not None and values["state_code"] != state_code:
            problems.append(f"entidad {values['state_code']} distinta de {state_code}")
        if problems:
            staged.issues.append(
                Issue(spec.name, "error", "invalid_record", "; ".join(problems), fid, key)
            )
            continue
        key_values = tuple(key.values())
        if key_values in seen:
            staged.issues.append(
                Issue(
                    spec.name,
                    "error",
                    "duplicate_key",
                    f"Llave natural repetida (ya vista en el FID {seen[key_values]}); se omite.",
                    fid,
                    key,
                )
            )
            continue
        seen[key_values] = fid
        if wkb is None and spec.geometry_required:
            staged.issues.append(
                Issue(spec.name, "error", "missing_geometry", "Registro sin geometría.", fid, key)
            )
            continue
        if wkb is None:
            staged.issues.append(
                Issue(
                    spec.name, "warning", "missing_geometry", "Se conserva sin geometría.", fid, key
                )
            )
        staged.rows.append((fid, *(values[c.name] for c in spec.columns), wkb))
    return staged
