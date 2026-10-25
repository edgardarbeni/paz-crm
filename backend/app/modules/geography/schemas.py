import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Level = Literal[
    "electoral_region",
    "state",
    "federal_district",
    "local_district",
    "municipality",
    "section",
    "locality",
    "neighborhood",
]


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class GeoNodeOut(Schema):
    id: uuid.UUID
    level: Level
    code: str = Field(description="Clave del nivel (número de sección, municipio, etc.).")
    key: str = Field(description="Clave INE legible: 01-0338, 01-005, C2…", examples=["01-0338"])
    name: str | None = None
    state_code: int | None = None
    electoral_region_id: uuid.UUID | None = None
    state_id: uuid.UUID | None = None
    municipality_id: uuid.UUID | None = None
    federal_district_id: uuid.UUID | None = None
    local_district_id: uuid.UUID | None = None


class NodeRef(Schema):
    id: uuid.UUID
    key: str
    name: str | None = None


class Ancestors(Schema):
    section: NodeRef
    municipality: NodeRef
    federal_district: NodeRef
    local_district: NodeRef
    state: NodeRef
    electoral_region: NodeRef | None


class GeoNodeDetail(GeoNodeOut):
    geometry: dict[str, Any] | None = Field(default=None, description="GeoJSON simplificado.")
    bbox: list[float] | None = Field(default=None, description="[oeste, sur, este, norte]")
    ancestors: Ancestors | None = None
    block_count: int | None = None


class FrameworkOut(Schema):
    id: uuid.UUID
    name: str
    cutoff_date: date | None
    source_agreement: str | None
    is_active: bool
    activated_at: datetime | None


class ImportRunOut(Schema):
    id: uuid.UUID
    framework_id: uuid.UUID
    state_code: int | None
    source_uri: str
    file_sha256: str | None
    source_srid: int | None
    layers_loaded: list[str]
    layers_missing: list[str]
    dry_run: bool
    status: str
    counts: dict[str, Any]
    warning_count: int
    error_count: int
    message: str | None
    started_at: datetime
    finished_at: datetime | None
    triggered_by: str | None


class ImportIssueOut(Schema):
    id: int
    layer: str
    source_fid: int | None
    natural_key: dict[str, Any] | None
    severity: str
    code: str
    message: str
