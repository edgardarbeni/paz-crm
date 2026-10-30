"""Intake outside the panel (phase 4): the public referral link with its proof of work, the field
app's idempotent batch and CSV/Excel imports with dry run (D-86, D-90, D-92)."""

import io
import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from openpyxl import Workbook
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core import pow as proof
from app.core.db.session import build_sessionmaker
from app.core.storage import ObjectStorage, build_storage
from app.modules.peace_movement import intake
from app.modules.people.service import Crypto
from tests.conftest import S3_ACCESS_KEY, S3_SECRET_KEY
from tests.integration.candidacies.conftest import Geo
from tests.integration.geography.conftest import rows, scalar
from tests.integration.peace_movement.conftest import API, curp, enroll, person
from tests.integration.peace_movement.test_houses import open_house
from tests.support import make_settings

PUBLIC = "/api/v1/public/peace-movement"


@pytest.fixture(autouse=True)
def instant_forms(monkeypatch: Any) -> None:
    monkeypatch.setattr(intake, "MIN_FILL_SECONDS", 0)


async def _public_body(
    client: AsyncClient, code: str, levels: dict[str, str], **person_fields: Any
) -> dict[str, Any]:
    form = (await client.get(f"{PUBLIC}/enroll/{code}")).json()
    challenge = proof.Challenge(
        form["challenge"]["algorithm"],
        form["challenge"]["challenge"],
        form["challenge"]["salt"],
        form["challenge"]["signature"],
        form["challenge"]["max_number"],
    )
    return {
        "referral_code": code,
        "person": {
            "given_names": "Lucía",
            "paternal_surname": "Pérez",
            "curp": curp(),
            "mobile": "4497776655",
            "street": "Calle Olivo",
            "state_code": 1,
            "section_number": 102,
            **person_fields,
        },
        "level_id": levels["pacifier"],
        "notice_version": form["notice"]["version"],
        "accepts_notice": True,
        "proof": {
            "challenge": challenge.challenge,
            "salt": challenge.salt,
            "number": proof.solve(challenge),
            "signature": challenge.signature,
        },
    }


async def test_public_form_and_enrollment(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
) -> None:
    recruiter = await enroll(client, root, levels, geo.sections[101])
    code = recruiter["referral_code"]
    assert (await client.get(f"{PUBLIC}/enroll/{'x' * 16}")).status_code == 404
    form = (await client.get(f"{PUBLIC}/enroll/{code}")).json()
    assert form["notice"]["version"] == "2026-10"
    assert len(form["levels"]) == 5
    assert "recruiter" not in form  # nobody learns who invited

    body = await _public_body(client, code, levels)
    sent = await client.post(f"{PUBLIC}/enroll", json=body)
    assert sent.status_code == 202, sent.text
    assert sent.json()["status"] == "received"
    created = (
        await rows(
            owner_engine,
            "SELECT m.status, m.channel, m.origin, m.recruited_by_member_id::text AS recruiter, "
            "m.registered_by_user_id, c.channel AS consent FROM peace_movement.members m "
            "JOIN people.privacy_consents c ON c.id = m.consent_id WHERE m.channel = "
            "'referral_link'",
        )
    )[0]
    assert created == {
        "status": "pending_validation",
        "channel": "referral_link",
        "origin": "recruiter",
        "recruiter": recruiter["id"],
        "registered_by_user_id": None,
        "consent": "referral_link",
    }
    # A solved challenge cannot be reused, nor a forged one accepted.
    replay = await client.post(f"{PUBLIC}/enroll", json=body)
    assert (replay.status_code, replay.json()["code"]) == (400, "invalid-challenge")
    forged = await _public_body(client, code, levels)
    forged["proof"]["signature"] = "0" * 64
    assert (await client.post(f"{PUBLIC}/enroll", json=forged)).status_code == 400


async def test_public_enrollment_never_reveals_a_curp(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
) -> None:
    recruiter = await enroll(client, root, levels, geo.sections[101])
    code = recruiter["referral_code"]
    member = await enroll(client, root, levels, geo.sections[101], recruiter=recruiter["id"])
    member_curp = (await client.get(f"{API}/members/{member['id']}", headers=root)).json()[
        "person"
    ]["curp"]
    known = await client.post("/api/v1/people", headers=root, json=person(geo.sections[105]))
    known_curp = known.json()["curp"]

    # Already a member: same answer, nothing new.
    again = await client.post(
        f"{PUBLIC}/enroll", json=await _public_body(client, code, levels, curp=member_curp)
    )
    assert again.status_code == 202
    # A registered person who is not a member: pending, with what was submitted kept aside.
    reused = await client.post(
        f"{PUBLIC}/enroll",
        json=await _public_body(client, code, levels, curp=known_curp, given_names="Otro"),
    )
    assert reused.status_code == 202
    pending = (
        await client.get(f"{API}/members", headers=root, params={"status": "pending_validation"})
    ).json()["items"]
    assert len(pending) == 1
    detail = (await client.get(f"{API}/members/{pending[0]['id']}", headers=root)).json()
    assert detail["person"]["given_names"] == "Juan"  # the stored person is not overwritten
    assert detail["intake"]["given_names"] == "Otro"
    stored = await scalar(
        owner_engine,
        "SELECT encode(intake_ciphertext, 'escape') FROM peace_movement.members WHERE id = :id",
        id=pending[0]["id"],
    )
    assert "Otro" not in stored  # encrypted at rest

    # The honeypot is accepted and dropped.
    trap = await _public_body(client, code, levels)
    trap["website"] = "http://spam.example"
    assert (await client.post(f"{PUBLIC}/enroll", json=trap)).status_code == 202
    assert (
        await scalar(
            owner_engine,
            "SELECT count(*) FROM peace_movement.members WHERE channel = 'referral_link'",
        )
        == 1
    )


async def test_public_enrollment_rules(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    monkeypatch: Any,
) -> None:
    recruiter = await enroll(client, root, levels, geo.sections[101])
    code = recruiter["referral_code"]
    refused = await _public_body(client, code, levels)
    refused["accepts_notice"] = False
    assert (await client.post(f"{PUBLIC}/enroll", json=refused)).status_code == 400
    stale = await _public_body(client, code, levels)
    stale["notice_version"] = "2025-01"
    assert (await client.post(f"{PUBLIC}/enroll", json=stale)).status_code == 409
    nowhere = await _public_body(client, code, levels, section_number=999)
    assert (await client.post(f"{PUBLIC}/enroll", json=nowhere)).status_code == 400

    monkeypatch.setattr(intake, "MIN_FILL_SECONDS", 60)
    hasty = await _public_body(client, code, levels)
    assert (await client.post(f"{PUBLIC}/enroll", json=hasty)).status_code == 400
    monkeypatch.setattr(intake, "MIN_FILL_SECONDS", 0)
    monkeypatch.setattr(intake, "PUBLIC_CODE_LIMIT", (1, 60))
    # A fresh link: the attempts above already count for the first one.
    code = (await enroll(client, root, levels, geo.sections[101]))["referral_code"]
    first = await client.post(f"{PUBLIC}/enroll", json=await _public_body(client, code, levels))
    assert first.status_code == 202
    second = await client.post(f"{PUBLIC}/enroll", json=await _public_body(client, code, levels))
    assert second.status_code == 429


async def test_batch_is_idempotent_and_reports_each_item(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
) -> None:
    host = await enroll(client, root, levels, geo.sections[101])
    contact = await enroll(client, root, levels, geo.sections[101], recruiter=host["id"])
    house = await open_house(
        client, root, owner_engine, geo.sections[101],
        opener=host["id"], host=host["id"], contact=contact["id"],
    )  # fmt: skip
    good, joins, bad = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    def item(client_id: uuid.UUID, **fields: Any) -> dict[str, Any]:
        return {
            "client_id": str(client_id),
            "captured_at": "2026-10-28T12:00:00-06:00",
            "capture_longitude": -102.29,
            "capture_latitude": 21.88,
            "person": person(geo.sections[102]),
            "level_id": levels["pacifier"],
            "recruiter_member_id": host["id"],
            "origin": "recruiter",
            "consent": {"channel": "paper"},
            **fields,
        }

    batch = {
        "items": [
            item(good),
            item(joins, house_id=house["id"]),
            item(bad, person=person(geo.sections[102], with_curp=False)),
        ]
    }
    first = await client.post(f"{API}/members/batch", headers=root, json=batch)
    assert first.status_code == 200, first.text
    assert (first.json()["accepted"], first.json()["errors"]) == (2, 1)
    statuses = {i["client_id"]: (i["status"], i["error_code"]) for i in first.json()["items"]}
    assert statuses[str(bad)] == ("error", "member-requirements")
    again = (await client.post(f"{API}/members/batch", headers=root, json=batch)).json()
    assert (again["duplicates"], again["accepted"]) == (2, 0)
    assert {i["member_id"] for i in again["items"] if i["status"] == "duplicate"} == {
        i["member_id"] for i in first.json()["items"] if i["status"] == "accepted"
    }

    joined = next(i for i in first.json()["items"] if i["client_id"] == str(joins))["member_id"]
    detail = (await client.get(f"{API}/members/{joined}", headers=root)).json()
    assert (detail["status"], detail["channel"], detail["requested_house_id"]) == (
        "pending_validation",
        "field_app",
        house["id"],
    )
    # Validating joins the house chosen while enrolling (D-96).
    await client.post(f"{API}/members/{joined}/validate", headers=root)
    members = (await client.get(f"{API}/houses/{house['id']}/members", headers=root)).json()
    assert {m["member"]["id"]: m["source"] for m in members}[joined] == "enrollment"
    assert (
        await scalar(
            owner_engine,
            "SELECT count(*) FROM peace_movement.member_intake_keys WHERE capture_location IS NOT NULL",
        )
        == 2
    )


@pytest.fixture
async def storage(app: FastAPI, s3_endpoint: str) -> Any:
    store = build_storage(
        make_settings(
            storage_endpoint=s3_endpoint,
            storage_bucket=f"i{uuid.uuid4().hex[:12]}",
            storage_access_key=S3_ACCESS_KEY,
            storage_secret_key=S3_SECRET_KEY,
        )
    )
    assert store is not None
    await store.ensure_bucket()
    app.state.storage = store
    yield store
    app.state.storage = None


async def _process(app: FastAPI, app_engine: AsyncEngine, storage: ObjectStorage) -> Any:
    services = app.state.identity
    crypto = Crypto(cipher=services.cipher, indexer=services.indexer)
    return await intake.process_next_import(build_sessionmaker(app_engine), storage, crypto)


async def test_imports_with_dry_run(  # noqa: PLR0917
    app: FastAPI,
    client: AsyncClient,
    root: dict[str, str],
    scoped: Any,
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
    app_engine: AsyncEngine,
    storage: ObjectStorage,
) -> None:
    leader, follower = curp(), curp()
    csv_text = (
        "Nombre,Apellido paterno,Apellido materno,CURP,Celular,Entidad,Sección,Nivel,"
        "CURP reclutador,Origen\n"
        f"Ana,Ruiz,,{leader},4491112233,1,101,Promotor de la Paz,,structure\n"
        f"Beto,Ruiz,,{follower},4491112234,1,103,pacifier,{leader},\n"
        f"Caro,Ruiz,,{curp()},4491112235,1,999,pacifier,,structure\n"
        "Dani,Ruiz,,,4491112236,1,101,pacifier,,structure\n"
    )

    def upload(dry_run: bool, name: str = "lista.csv", data: bytes | None = None) -> Any:
        return client.post(
            f"{API}/imports",
            headers=root,
            files={"file": (name, data if data is not None else csv_text.encode(), "text/csv")},
            data={"dry_run": str(dry_run).lower(), "evidence_uri": "s3://pazos/consents/lote1.pdf"},
        )

    queued = await upload(True)
    assert queued.status_code == 202, queued.text
    assert (queued.json()["status"], queued.json()["dry_run"]) == ("queued", True)
    run = await _process(app, app_engine, storage)
    assert (run.status, run.total_rows, run.accepted_rows, run.error_rows) == ("done", 4, 2, 2)
    assert await scalar(owner_engine, "SELECT count(*) FROM peace_movement.members") == 0
    errors = (await client.get(f"{API}/imports/{run.id}/errors", headers=root)).json()["items"]
    assert [(e["row_number"], e["code"]) for e in errors] == [
        (4, "bad-request"),
        (5, "bad-request"),
    ]

    await upload(False)
    real = await _process(app, app_engine, storage)
    assert (real.status, real.accepted_rows) == ("done", 2)
    imported = await rows(
        owner_engine,
        "SELECT status, channel, depth FROM peace_movement.members ORDER BY depth",
    )
    assert imported == [
        {"status": "active", "channel": "import", "depth": 0},
        {"status": "active", "channel": "import", "depth": 1},
    ]
    # Imported rows are audited in bulk, one entry per chunk (D-90, D-98): the recruiter and
    # its recruit go in different waves, so two entries.
    bulk = await rows(
        owner_engine,
        "SELECT after FROM audit.audit_log WHERE action = 'member_import' "
        "AND after->>'run_id' = :run",
        run=str(real.id),
    )
    assert sorted(entry["after"]["count"] for entry in bulk) == [1, 1]
    row_entries = await scalar(
        owner_engine,
        "SELECT count(*) FROM audit.audit_log a JOIN peace_movement.members m "
        "ON a.entity_id IN (m.id::text, m.person_id::text) "
        "WHERE a.entity_table IN ('people.persons', 'peace_movement.members')",
    )
    assert row_entries == 0
    listed = (await client.get(f"{API}/imports", headers=root)).json()["items"]
    assert [r["dry_run"] for r in listed] == [False, True]

    # Excel works too; other formats are refused.
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["Nombre", "Apellido paterno", "CURP", "Entidad", "Sección"])
    sheet.append(["Eva", "Luna", curp(), 1, 104])
    buffer = io.BytesIO()
    book.save(buffer)
    excel = await upload(False, "lista.xlsx", buffer.getvalue())
    assert excel.status_code == 202
    excel_run = await _process(app, app_engine, storage)
    assert (excel_run.accepted_rows, excel_run.error_rows) == (0, 1)  # no level, no default
    assert (await upload(True, "lista.pdf")).status_code == 400
    with_default = await client.post(
        f"{API}/imports",
        headers=root,
        files={"file": ("lista.xlsx", buffer.getvalue(), "application/octet-stream")},
        data={"dry_run": "false", "evidence_uri": "s3://x", "default_level_id": levels["pacifier"]},
    )
    assert with_default.status_code == 202
    assert (await _process(app, app_engine, storage)).accepted_rows == 1
    assert await _process(app, app_engine, storage) is None  # queue empty

    _, capturist = await scoped(("capturist",), [{"level": "national"}])
    assert (await client.get(f"{API}/imports", headers=capturist)).status_code == 403
    missing = await client.get(f"{API}/imports/{uuid.uuid4()}", headers=root)
    assert missing.status_code == 404


async def test_import_dependencies_between_rows(  # noqa: PLR0917
    app: FastAPI,
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
    app_engine: AsyncEngine,
    storage: ObjectStorage,
) -> None:
    broken, orphan, first, second = curp(), curp(), curp(), curp()
    csv_text = (
        "nombre;apellido_paterno;curp;entidad;seccion;nivel;curp_reclutador\n"
        f"Malo;Uno;{broken};1;999;pacifier;\n"  # row 2: bad section
        f"Hijo;Dos;{orphan};1;101;pacifier;{broken}\n"  # row 3: its recruiter failed
        f"Ciclo;Tres;{first};1;101;pacifier;{second}\n"  # rows 4-5: a cycle
        f"Ciclo;Cuatro;{second};1;101;pacifier;{first}\n"
    )
    for dry_run in (True, False):
        queued = await client.post(
            f"{API}/imports",
            headers=root,
            files={"file": ("dependencias.csv", csv_text.encode(), "text/csv")},
            data={"dry_run": str(dry_run).lower(), "evidence_uri": "s3://pazos/c/2.pdf"},
        )
        assert queued.status_code == 202
        run = await _process(app, app_engine, storage)
        assert (run.accepted_rows, run.error_rows) == (0, 4), dry_run
        errors = (await client.get(f"{API}/imports/{run.id}/errors", headers=root)).json()["items"]
        assert [(e["row_number"], e["code"]) for e in errors] == [
            (2, "bad-request"),
            (3, "recruiter-row-failed"),
            (4, "recruiter-cycle"),
            (5, "recruiter-cycle"),
        ]
    assert await scalar(owner_engine, "SELECT count(*) FROM peace_movement.members") == 0
