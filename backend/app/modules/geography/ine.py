"""INE public downloads (D-16): BGD shapefiles and tabular catalogs, indexed by the SIGE API
behind https://cartografia.ine.mx/sige8/productosCartograficos/bases.

Files are saved per state with stable names and a manifest (URL, SHA-256, cutoff) so imports
are reproducible:

    <dest>/<NN>/bgd/<NN NAME>.7z
    <dest>/<NN>/catalogos/{secciones.txt, localidades_seccion.txt, colonias.xls}
    <dest>/<NN>/manifest.json
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import quote

import httpx

from app.core.config import Settings
from app.modules.geography.importer.catalogs import (
    LOCALITIES_FILE,
    NEIGHBORHOODS_FILE,
    SECTIONS_FILE,
)

# producto → (local file name, wanted extension)
CATALOGS = {
    "Csecc": (SECTIONS_FILE, ".txt"),
    "CLS": (LOCALITIES_FILE, ".txt"),
    "CCol": (NEIGHBORHOODS_FILE, ".xls"),
}
_CUTOFF = re.compile(r"CORTE_([0-9]{1,2}[A-Z]{3}[0-9]{4})")


class IneDownloadError(Exception):
    pass


@dataclass
class DownloadedFile:
    kind: str
    url: str
    path: str
    sha256: str
    bytes: int


@dataclass
class Manifest:
    state_code: int
    bgd_cutoff: str | None = None
    catalogs_cutoff: str | None = None
    files: list[DownloadedFile] = field(default_factory=list)

    def save(self, folder: Path) -> Path:
        path = folder / "manifest.json"
        path.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return path

    @classmethod
    def load(cls, folder: Path) -> "Manifest | None":
        path = folder / "manifest.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        data["files"] = [DownloadedFile(**item) for item in data.get("files", [])]
        return cls(**data)


class IneClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.api = settings.ine_api_base_url.rstrip("/")
        self.storage = settings.ine_storage_base_url
        self.client = client

    async def _index(self, endpoint: str, **params: str | int) -> list[dict[str, str]]:
        response = await self.client.get(f"{self.api}/{endpoint}", params=params)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise IneDownloadError(f"Respuesta inesperada de {endpoint}: {data!r}")
        return data

    def url_for(self, item: dict[str, str]) -> str:
        return self.storage + quote(f"{item['path']}{item['archivo']}")

    async def bgd_item(self, state_code: int) -> dict[str, str]:
        items = await self._index("bases/", producto="bgd", entidad=state_code, formato="Shapefile")
        if len(items) != 1:
            raise IneDownloadError(
                f"Se esperaba un archivo BGD para el estado {state_code}: {items}"
            )
        return items[0]

    async def catalog_item(self, product: str, state_code: int) -> dict[str, str]:
        _, extension = CATALOGS[product]
        marker = f"/ENTIDAD/{state_code}/"
        for item in await self._index("catalogos", producto=product):
            if marker in item["path"] and item["archivo"].lower().endswith(extension):
                return item
        raise IneDownloadError(
            f"No se encontró el catálogo {product} ({extension}) del estado {state_code}"
        )

    async def fetch(self, url: str, destination: Path) -> DownloadedFile:
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        async with self.client.stream("GET", url) as response:
            response.raise_for_status()
            with destination.open("wb") as handle:
                async for chunk in response.aiter_bytes():
                    handle.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
        return DownloadedFile(
            kind="", url=url, path=str(destination), sha256=digest.hexdigest(), bytes=size
        )


def cutoff_of(path: str) -> str | None:
    match = _CUTOFF.search(path)
    return match.group(1) if match else None


async def download_state(
    settings: Settings, state_code: int, dest: Path, *, include_bgd: bool = True
) -> Manifest:
    folder = dest / f"{state_code:02d}"
    manifest = Manifest(state_code=state_code)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(60, read=600), follow_redirects=False
    ) as http:
        ine = IneClient(settings, http)
        if include_bgd:
            item = await ine.bgd_item(state_code)
            downloaded = await ine.fetch(ine.url_for(item), folder / "bgd" / item["archivo"])
            downloaded.kind = "bgd"
            manifest.files.append(downloaded)
            manifest.bgd_cutoff = item["path"].split("/")[0]
        for product, (name, _) in CATALOGS.items():
            item = await ine.catalog_item(product, state_code)
            downloaded = await ine.fetch(ine.url_for(item), folder / "catalogos" / name)
            downloaded.kind = f"catalog:{product}"
            manifest.files.append(downloaded)
            manifest.catalogs_cutoff = manifest.catalogs_cutoff or cutoff_of(item["path"])
    manifest.save(folder)
    return manifest
