"""Reading BGD shapefiles (D-18): a folder or the official 7z, one layer at a time.

- Field names are normalized to lower case and mapped by name, never by position (§1.5).
- Text encoding: the `.cpg` when present, otherwise CP1252 (§1.4, verified on 1,596 files).
- Geometries stay as WKB in the source CRS; reprojection and repair happen in PostGIS.
"""

import hashlib
import math
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import py7zr
import pyogrio.raw

NO_NAME = re.compile(r"^\s*SIN\s+NOMBRE\s*$", re.IGNORECASE)
_EPSG = re.compile(r"EPSG:(\d+)")


class SourceError(Exception):
    """The source cannot be imported (missing required layer, unreadable file, mixed CRS)."""


@dataclass(frozen=True, slots=True)
class LayerData:
    name: str
    srid: int
    fids: list[int]
    wkb: list[bytes | None]
    columns: dict[str, list[Any]]

    def __len__(self) -> int:
        return len(self.fids)

    def records(self) -> Iterator[tuple[int, bytes | None, dict[str, Any]]]:
        names = list(self.columns)
        for index, fid in enumerate(self.fids):
            yield fid, self.wkb[index], {name: self.columns[name][index] for name in names}


@dataclass
class BgdSource:
    """A state folder with the BGD shapefiles (``01 AGUASCALIENTES/``)."""

    folder: Path
    uri: str
    files: dict[str, Path] = field(default_factory=dict)

    @classmethod
    def from_folder(cls, folder: Path, uri: str | None = None) -> "BgdSource":
        if not folder.is_dir():
            raise SourceError(f"No existe la carpeta {folder}")
        files = {
            path.stem.upper(): path for path in folder.iterdir() if path.suffix.lower() == ".shp"
        }
        if not files:
            raise SourceError(f"La carpeta {folder} no contiene shapefiles")
        return cls(folder=folder, uri=uri or str(folder), files=files)

    def has(self, layer: str) -> bool:
        return layer in self.files

    def sha256(self, layers: list[str]) -> str:
        """Fingerprint of the imported layers (.shp + .dbf), for idempotency reports."""
        digest = hashlib.sha256()
        for layer in sorted(name for name in layers if name in self.files):
            shp = self.files[layer]
            for path in sorted(shp.parent.glob(f"{shp.stem}.*")):
                if path.suffix.lower() in {".shp", ".dbf"}:
                    digest.update(path.name.upper().encode())
                    digest.update(path.read_bytes())
        return digest.hexdigest()

    def read(self, layer: str) -> LayerData:
        path = self.files[layer]
        has_cpg = any(path.with_suffix(ext).exists() for ext in (".cpg", ".CPG"))
        try:
            meta, fids, geometry, field_data = pyogrio.raw.read(
                path, encoding=None if has_cpg else "cp1252", return_fids=True
            )
        except Exception as exc:  # pyogrio raises several driver-specific errors
            raise SourceError(f"No se pudo leer {path.name}: {exc}") from exc
        match = _EPSG.search(str(meta.get("crs") or ""))
        if match is None:
            raise SourceError(f"{path.name} no declara un CRS EPSG")
        names = [str(name).lower() for name in meta["fields"]]
        columns = {name: [_clean(value) for value in field_data[i]] for i, name in enumerate(names)}
        return LayerData(
            name=layer,
            srid=int(match.group(1)),
            fids=[int(fid) for fid in fids],
            wkb=[bytes(g) if g is not None else None for g in geometry],
            columns=columns,
        )


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        return None if not value or NO_NAME.match(value) else value
    return value


@contextmanager
def open_source(path: Path, *, state_code: int) -> Iterator[BgdSource]:
    """Accepts a state folder, a parent folder containing ``NN NAME/`` or a ``.7z`` file."""
    if path.is_file() and path.suffix.lower() == ".7z":
        with tempfile.TemporaryDirectory(prefix="paz-bgd-") as tmp:
            with py7zr.SevenZipFile(path) as archive:
                archive.extractall(tmp)
            yield BgdSource.from_folder(_state_folder(Path(tmp), state_code), uri=str(path))
        return
    yield BgdSource.from_folder(_state_folder(path, state_code), uri=str(path))


def _state_folder(path: Path, state_code: int) -> Path:
    if not path.is_dir():
        raise SourceError(f"No existe la carpeta {path}")
    if any(child.suffix.lower() == ".shp" for child in path.iterdir()):
        return path
    prefix = f"{state_code:02d} "
    matches = [
        child for child in path.iterdir() if child.is_dir() and child.name.startswith(prefix)
    ]
    if len(matches) != 1:
        raise SourceError(f"No se encontró la carpeta del estado {state_code:02d} en {path}")
    return matches[0]
