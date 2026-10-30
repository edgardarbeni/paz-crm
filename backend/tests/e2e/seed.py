"""Seed for the panel's end-to-end tests (Playwright against the real stack, D-73).

Loads the synthetic BGD (tests/fixtures/bgd.py) as the active framework, creates one user per
E2E scenario (TOTP secrets are known so the browser test can compute codes), a configured
local process, people and a couple of nominations. Writes credentials and ids to a JSON file.

    uv run python -m tests.e2e.seed ../frontend/e2e/.seed.json

Refuses to run outside development/test environments.
"""

import asyncio
import json
import sys
import tempfile
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pyotp
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import col

from app.core.config import Environment, get_settings
from app.core.crypto import build_blind_indexer, build_field_cipher
from app.core.db.session import build_engine, build_sessionmaker
from app.modules.candidacies import nominations, service
from app.modules.candidacies.models import OfficeType, Party
from app.modules.candidacies.schemas import (
    FormulaIn,
    MunicipalitySettingIn,
    NominationIn,
    ProcessIn,
    ProcessOfficeIn,
)
from app.modules.geography.importer.run import ImportOptions, import_state
from app.modules.identity import repository as repo
from app.modules.identity.models import (
    ScopeLevel,
    TotpCredential,
    User,
    UserRole,
    UserScope,
    UserStatus,
)
from app.modules.identity.security.passwords import Passwords
from app.modules.identity.services.auth import TOTP_CONTEXT
from app.modules.identity.services.scopes import GeoScope, rebuild_scope_sections
from app.modules.peace_movement import aggregates, members
from app.modules.peace_movement.models import EnrollmentChannel, MemberStatus
from app.modules.peace_movement.schemas import ConsentCapture, EnrollmentIn
from app.modules.people import curp as curp_rules
from app.modules.people.schemas import AddressIn, PersonCreate
from app.modules.people.service import Crypto, create_person, publish_notice
from tests.fixtures.bgd import build_catalogs, build_state

PASSWORD = "e2e-contrasena-segura-2026"
# scenario → (roles, with TOTP)
USERS: dict[str, tuple[tuple[str, ...], bool]] = {
    "login": (("superadmin",), True),
    "enroll": (("admin",), False),
    "capture": (("superadmin",), True),
    "substitute": (("superadmin",), True),
    "scoped": (("coordinator",), True),
    "geography": (("superadmin",), True),
    "peace": (("superadmin",), True),
}
PEOPLE = [
    ("Ana", "Ramírez", "M"), ("Beatriz", "Soto", "M"), ("Carla", "Núñez", "M"), ("Diana", "Ortiz", "M"),
    ("Elena", "Vega", "M"), ("Fernanda", "Ríos", "M"), ("Gabriela", "Luna", "M"), ("Helena", "Mora", "M"),
    ("Irene", "Paz", "M"), ("Julia", "Cano", "M"), ("Karla", "Solís", "M"), ("Laura", "Peña", "M"),
    ("Mario", "Fuentes", "H"), ("Néstor", "Galindo", "H"),
]  # fmt: skip


async def _ids(db: AsyncSession, sql: str) -> dict[int, uuid.UUID]:
    return {row[0]: row[1] for row in (await db.execute(text(sql))).all()}


async def seed() -> dict[str, Any]:  # noqa: PLR0915 - one linear script
    settings = get_settings()
    if settings.environment not in {Environment.DEVELOPMENT, Environment.TEST}:
        raise SystemExit("La semilla E2E solo corre en development o test.")
    owner = create_async_engine(str(settings.async_migrations_database_url))
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_state(root)
        build_catalogs(root)
        await import_state(
            owner,
            settings,
            ImportOptions(
                source=root,
                state_code=1,
                framework_name="INE sintético E2E",
                cutoff_date=date(2025, 12, 15),
                catalogs=root / "catalogos",
                catalogs_cutoff="19ENE2026",
                triggered_by="e2e-seed",
            ),
        )
    await owner.dispose()

    engine = build_engine(settings)
    passwords = Passwords(settings)
    cipher = build_field_cipher(settings)
    crypto = Crypto(cipher=cipher, indexer=build_blind_indexer(settings))
    result: dict[str, Any] = {"password": PASSWORD, "users": {}}
    async with build_sessionmaker(engine)() as db:
        geo = {
            "state": (await db.execute(text("SELECT id FROM geography.states"))).scalar_one(),
            "municipalities": await _ids(
                db, "SELECT municipality_code, id FROM geography.municipalities"
            ),
            "local_districts": await _ids(
                db, "SELECT district_number, id FROM geography.local_districts"
            ),
        }
        user_ids: dict[str, uuid.UUID] = {}
        for key, (roles, with_totp) in USERS.items():
            email = f"e2e-{key}@example.com"
            user = User(
                email=email,
                full_name=f"E2E {key}",
                status=UserStatus.ACTIVE,
                password_hash=passwords.hash(PASSWORD),
            )
            db.add(user)
            await db.flush()
            assert user.id is not None
            for code in roles:
                role = await repo.role_by_code(db, code)
                assert role is not None
                assert role.id is not None
                db.add(UserRole(user_id=user.id, role_id=role.id))
            secret = None
            if with_totp:
                secret = pyotp.random_base32(32)
                blob = cipher.encrypt(secret, context=TOTP_CONTEXT)
                db.add(
                    TotpCredential(
                        user_id=user.id,
                        secret_ciphertext=blob,
                        key_version=cipher.key_version(blob),
                        confirmed_at=datetime.now(UTC),
                    )
                )
            user_ids[key] = user.id
            result["users"][key] = {"email": email, "totp_secret": secret}
        db.add(
            UserScope(
                user_id=user_ids["scoped"],
                scope_level=ScopeLevel.MUNICIPALITY,
                municipality_id=geo["municipalities"][1],
            )
        )
        await db.flush()
        await rebuild_scope_sections(db, user_ids["scoped"])
        await db.commit()

        process = await service.create_process(
            db,
            ProcessIn(
                name="Proceso Local E2E 2027",
                election_year=2027,
                election_level="local",
                state_id=geo["state"],
            ),
        )
        assert process.id is not None
        offices = {o.code: o.id for o in (await db.execute(select(OfficeType))).scalars()}

        def member(code: str) -> ProcessOfficeIn:
            return ProcessOfficeIn(
                office_type_id=offices[code],
                is_enabled=True,
                slate_parent_office_type_id=offices["municipal_president"],
            )

        await service.configure_offices(
            db,
            process.id,
            [
                ProcessOfficeIn(office_type_id=offices["municipal_president"], is_enabled=True),
                member("syndic"),
                member("councilor_mr"),
                member("councilor_rp"),
                ProcessOfficeIn(office_type_id=offices["local_deputy_mr"], is_enabled=True),
            ],
        )
        await service.configure_municipalities(
            db,
            process.id,
            [
                MunicipalitySettingIn(
                    municipality_id=geo["municipalities"][1],
                    syndic_count=1,
                    mr_councilor_count=2,
                    rp_councilor_count=1,
                ),
                MunicipalitySettingIn(
                    municipality_id=geo["municipalities"][2],
                    syndic_count=1,
                    mr_councilor_count=2,
                    rp_councilor_count=1,
                ),
            ],
        )
        everyone = GeoScope(user_id=user_ids["login"], unrestricted=True)
        people = []
        for given, surname, sex in PEOPLE:
            view = await create_person(
                db,
                crypto,
                everyone,
                PersonCreate(
                    given_names=given, paternal_surname=surname, maternal_surname="E2E", sex=sex
                ),
                can_accept_incoherence=False,
            )
            people.append({"id": str(view.person.id), "name": f"{given} {surname} E2E", "sex": sex})
        paz = (
            (await db.execute(select(Party).where(col(Party.is_own_party).is_(True))))
            .scalars()
            .one()
        )
        actor = nominations.Actor(
            user_id=user_ids["login"], geo=everyone, can_approve=True, can_override=True
        )
        seeded = {}
        for district in (1, 2):
            nomination = await nominations.create_nomination(
                db,
                actor,
                NominationIn(
                    process_id=process.id,
                    office_type_id=offices["local_deputy_mr"],
                    node_id=geo["local_districts"][district],
                    party_id=paz.id,
                ),
            )
            seeded[f"local_district_{district}"] = str(nomination.id)
        owner_person, substitute_person = people[10], people[11]
        await nominations.create_formula(
            db,
            actor,
            uuid.UUID(seeded["local_district_1"]),
            FormulaIn(
                office_type_id=offices["local_deputy_mr"],
                position=1,
                owner_person_id=uuid.UUID(owner_person["id"]),
                substitute_person_id=uuid.UUID(substitute_person["id"]),
            ),
        )
        result["peace"] = await _seed_peace_movement(db, crypto, user_ids["peace"], geo)
        result.update(
            process_id=str(process.id),
            municipality_1=str(geo["municipalities"][1]),
            people=people[:10],
            substitute_candidate=people[12],
            nominations=seeded,
            seeded_formula={"owner": owner_person["name"], "substitute": substitute_person["name"]},
        )
    await engine.dispose()
    return result


def _curp(index: int) -> str:
    """Valid CURP of a man born in Aguascalientes on January (index + 1), 1990."""
    prefix = f"MOPA9001{index + 1:02d}HASRZS0"
    return prefix + curp_rules.check_digit(prefix)


async def _seed_peace_movement(
    db: AsyncSession, crypto: Crypto, user_id: uuid.UUID, geo: dict[str, Any]
) -> dict[str, Any]:
    """A sample notice, a small pyramid (an Ambassador with recruits) and one pending
    enrollment."""
    await publish_notice(
        db,
        code="peace_movement",
        version="e2e",
        title="Aviso de privacidad del Movimiento de Paz (ejemplo)",
        body="Texto de ejemplo del aviso para las pruebas de extremo a extremo del panel.",
        is_sample=True,
    )
    sections = await _ids(db, "SELECT section_number, id FROM geography.sections")
    levels: dict[str, uuid.UUID] = dict(
        (await db.execute(text("SELECT code, id FROM peace_movement.participation_levels"))).all()
    )
    actor = members.Actor(user_id=user_id, geo=GeoScope(user_id=user_id, unrestricted=True))
    people = [
        ("Rosa", "Embajadora"),
        ("Tomás", "Recluta"),
        ("Úrsula", "Recluta"),
        ("Víctor", "Pendiente"),
    ]
    created: list[Any] = []
    for index, (given, surname) in enumerate(people):
        recruiter = created[0].id if created else None
        body = EnrollmentIn(
            person=PersonCreate(
                given_names=given,
                paternal_surname=surname,
                maternal_surname="E2E",
                curp=_curp(index),
                address=AddressIn(street="Calle de la Paz", section_id=sections[101 + index]),
            ),
            level_id=levels["peace_ambassador" if index == 0 else "pacifier"],
            recruiter_member_id=recruiter,
            origin="recruiter" if recruiter else "structure",
            consent=ConsentCapture(),
        )
        status = MemberStatus.PENDING_VALIDATION if surname == "Pendiente" else MemberStatus.ACTIVE
        created.append(
            await members.enroll(
                db,
                crypto,
                actor,
                body,
                channel=EnrollmentChannel.PANEL
                if status == MemberStatus.ACTIVE
                else EnrollmentChannel.FIELD_APP,
                status=status,
            )
        )
    root, first, second, pending = created
    await db.execute(
        text("UPDATE peace_movement.members SET channel = 'referral_link' WHERE id = :id"),
        {"id": pending.id},
    )
    await db.commit()
    await aggregates.rebuild_all(db)  # the scheduler is not running in E2E
    return {
        "root": {
            "id": str(root.id),
            "person_id": str(root.person_id),
            "name": "Rosa Embajadora E2E",
            "code": root.referral_code,
        },
        "recruits": [str(first.id), str(second.id)],
        "pending": {"id": str(pending.id), "name": "Víctor Pendiente E2E"},
        "next_curp": _curp(10),
        "public_curp": _curp(11),
    }


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "e2e-seed.json")
    out.write_text(json.dumps(asyncio.run(seed()), ensure_ascii=False, indent=2))
    print(f"Semilla E2E escrita en {out}")  # noqa: T201
