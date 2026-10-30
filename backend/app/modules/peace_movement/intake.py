"""Intake of members outside the panel (phase 4): the public referral link, the field app's
idempotent batch upload and CSV/Excel imports (docs/modules/peace-movement.md, D-86, D-90, D-92).

- **Public link:** no session. Defended by a self-hosted proof of work, a honeypot, a minimum
  fill time and rate limits per IP and per referral code. The answer is the same whether or
  not the CURP was registered; enrollments arrive `pending_validation`.
- **Batch upload:** each item carries a device UUID; resending it never duplicates. Items run
  in their own savepoints, so one error does not sink the batch.
- **Imports:** the file goes to S3 and the scheduler processes it (D-84). A dry run validates
  every row and rolls back. Imports by a coordinator or admin enter active (D-92); people
  tables are audited with one bulk entry per chunk, members row by row (D-90).
"""

import asyncio
import csv
import io
import json
import time
import unicodedata
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from geoalchemy2 import WKTElement
from openpyxl import load_workbook
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import col

from app.core import pow as proof
from app.core.audit import record_bulk
from app.core.db.base import pk
from app.core.errors import AppError, BadRequestError, ConflictError, NotFoundError
from app.core.logging import get_logger
from app.core.pagination import CursorPage, PageParams, paginate, parse_sort
from app.core.rate_limit import RateLimiter
from app.core.storage import ObjectStorage
from app.modules.identity.services.access import load_access
from app.modules.identity.services.scopes import GeoScope, resolve_scope
from app.modules.peace_movement import catalog, members
from app.modules.peace_movement.members import Actor
from app.modules.peace_movement.models import (
    EnrollmentChannel,
    ImportStatus,
    Member,
    MemberImportError,
    MemberImportRun,
    MemberIntakeKey,
    MemberOrigin,
    MemberStatus,
    ParticipationLevel,
)
from app.modules.peace_movement.permissions import PeacePerm
from app.modules.peace_movement.schemas import (
    BatchIn,
    BatchItemOut,
    ConsentCapture,
    EnrollmentIn,
    PublicEnrollmentIn,
)
from app.modules.people import service as people
from app.modules.people.models import Person
from app.modules.people.schemas import AddressIn, ContactIn, PersonCreate

logger = get_logger(__name__)

INTAKE_CONTEXT = "peace_movement.members.intake"
PUBLIC_IP_LIMIT = (20, 3600)  # enrollments per IP per hour
PUBLIC_CODE_LIMIT = (100, 24 * 3600)  # enrollments per referral code per day
MIN_FILL_SECONDS = 3
IMPORT_MAX_BYTES = 20 * 1024 * 1024
IMPORT_MAX_ROWS = 100_000
IMPORT_CHUNK = 250  # rows per transaction
IMPORT_WORKERS = 4  # chunks processed at once
IMPORT_TYPES = {".csv": "text/csv", ".xlsx": "application/vnd.openxmlformats-officedocument"}
# Tables written per imported row; audited with one bulk entry per chunk (D-90, D-98).
BULK_AUDITED = frozenset(
    {
        "people.persons",
        "people.person_contacts",
        "people.person_addresses",
        "people.privacy_consents",
        "peace_movement.members",
    }
)
UNRESTRICTED = GeoScope(user_id=uuid.UUID(int=0), unrestricted=True)


async def _section(
    db: AsyncSession,
    state_code: int,
    section_number: int,
    cache: dict[tuple[int, int], uuid.UUID] | None = None,
) -> uuid.UUID:
    if cache is not None and (state_code, section_number) in cache:
        return cache[(state_code, section_number)]
    found = await db.execute(
        text(
            "SELECT s.id FROM geography.sections s JOIN geography.states st ON st.id = s.state_id "
            "WHERE st.state_code = :state AND s.section_number = :section AND s.is_active"
        ),
        {"state": state_code, "section": section_number},
    )
    section_id: uuid.UUID | None = found.scalar_one_or_none()
    if section_id is None:
        raise BadRequestError(
            f"No existe la sección {section_number:04d} en la entidad {state_code:02d}."
        )
    if cache is not None:
        cache[(state_code, section_number)] = section_id
    return section_id


# --- public link ------------------------------------------------------------------------------


async def recruiter_by_code(db: AsyncSession, referral_code: str) -> Member:
    recruiter = (
        await db.execute(
            select(Member).where(
                col(Member.referral_code) == referral_code,
                col(Member.status) == MemberStatus.ACTIVE,
                col(Member.deleted_at).is_(None),
            )
        )
    ).scalar_one_or_none()
    if recruiter is None:
        raise NotFoundError("El enlace de inscripción no es válido.")
    return recruiter


async def public_form(
    db: AsyncSession, key: bytes, referral_code: str
) -> tuple[Any, list[ParticipationLevel], proof.Challenge]:
    await recruiter_by_code(db, referral_code)
    notice = await people.current_notice(db, members.NOTICE_CODE)
    if notice is None:
        raise members.NoticeUnavailableError("La inscripción no está disponible por ahora.")
    return notice, await catalog.list_levels(db), proof.create_challenge(key)


async def public_enroll(  # noqa: PLR0917
    db: AsyncSession,
    crypto: people.Crypto,
    redis: Redis,
    limiter: RateLimiter,
    key: bytes,
    body: PublicEnrollmentIn,
    *,
    client_ip: str | None,
) -> None:
    """Pending enrollment from a member's link. Silent for honeypots and existing members, so
    the answer never tells whether a CURP was registered."""
    issued = await proof.verify(
        redis,
        key,
        proof.Solution(
            challenge=body.proof.challenge,
            salt=body.proof.salt,
            number=body.proof.number,
            signature=body.proof.signature,
        ),
    )
    if body.website:  # a bot filled the hidden field: accept and drop
        logger.info("public_enrollment_honeypot")
        return
    if time.time() - issued < MIN_FILL_SECONDS:
        raise BadRequestError("El formulario se envió demasiado rápido; inténtalo de nuevo.")
    ip_limit, ip_window = PUBLIC_IP_LIMIT
    code_limit, code_window = PUBLIC_CODE_LIMIT
    await limiter.hit(
        "pm_enroll_ip", client_ip or "unknown", limit=ip_limit, window_seconds=ip_window
    )
    await limiter.hit(
        "pm_enroll_code", body.referral_code, limit=code_limit, window_seconds=code_window
    )
    if not body.accepts_notice:
        raise BadRequestError("Para inscribirte debes aceptar el aviso de privacidad.")
    recruiter = await recruiter_by_code(db, body.referral_code)
    notice = await people.current_notice(db, members.NOTICE_CODE)
    if notice is None:
        raise members.NoticeUnavailableError("La inscripción no está disponible por ahora.")
    if notice.version != body.notice_version:
        raise ConflictError("El aviso de privacidad cambió; vuelve a cargar el formulario.")
    level = await catalog.get_level(db, body.level_id)
    section_id = await _section(db, body.person.state_code, body.person.section_number)
    data = body.person
    contacts = [ContactIn(contact_type="mobile", value=data.mobile, is_primary=True)]
    if data.email:
        contacts.append(ContactIn(contact_type="email", value=data.email))
    submitted = PersonCreate(
        given_names=data.given_names,
        paternal_surname=data.paternal_surname,
        maternal_surname=data.maternal_surname,
        curp=data.curp,
        contacts=contacts,
        address=AddressIn(
            street=data.street,
            exterior_number=data.exterior_number,
            postal_code=data.postal_code,
            section_id=section_id,
        ),
    )
    existing = (
        await db.execute(
            select(Person).where(
                col(Person.curp_hash) == crypto.curp_hash(data.curp),
                col(Person.deleted_at).is_(None),
            )
        )
    ).scalar_one_or_none()
    intake: bytes | None = None
    if existing is None:
        person = (
            await people.build_person(
                db,
                crypto,
                UNRESTRICTED,
                submitted,
                can_accept_incoherence=False,
                address_outside_scope=True,
            )
        ).person
    else:
        # Never overwrite the stored person: keep what was submitted for the validator.
        person = existing
        intake = crypto.cipher.encrypt(
            json.dumps(submitted.model_dump(mode="json"), ensure_ascii=False),
            context=INTAKE_CONTEXT,
        )
    try:
        await members.register(
            db,
            person=person,
            level=level,
            recruiter=recruiter,
            origin=MemberOrigin.RECRUITER,
            origin_detail=None,
            channel=EnrollmentChannel.REFERRAL_LINK,
            status=MemberStatus.PENDING_VALIDATION,
            registered_by=None,
            consent_channel=EnrollmentChannel.REFERRAL_LINK.value,
            evidence_uri=None,
            intake_ciphertext=intake,
            intake_key_version=crypto.cipher.key_version(intake) if intake else None,
        )
    except members.AlreadyEnrolledError:
        await db.rollback()
        logger.info("public_enrollment_already_enrolled")
        return
    await db.commit()


def decoded_intake(crypto: people.Crypto, member: Member) -> dict[str, Any] | None:
    if member.intake_ciphertext is None:
        return None
    value: dict[str, Any] = json.loads(
        crypto.cipher.decrypt(member.intake_ciphertext, context=INTAKE_CONTEXT)
    )
    return value


# --- field app batch ----------------------------------------------------------------------------


async def submit_batch(
    db: AsyncSession, crypto: people.Crypto, actor: Actor, body: BatchIn
) -> list[BatchItemOut]:
    results: list[BatchItemOut] = []
    for item in body.items:
        known = await db.get(MemberIntakeKey, item.client_id)
        if known is not None:
            results.append(
                BatchItemOut(
                    client_id=item.client_id, status="duplicate", member_id=known.member_id
                )
            )
            continue
        try:
            async with db.begin_nested():
                member = await members.enroll(
                    db,
                    crypto,
                    actor,
                    item,
                    channel=EnrollmentChannel.FIELD_APP,
                    status=MemberStatus.PENDING_VALIDATION,
                    commit=False,
                )
                location = None
                if item.capture_longitude is not None and item.capture_latitude is not None:
                    location = WKTElement(
                        f"POINT({item.capture_longitude} {item.capture_latitude})", srid=4326
                    )
                db.add(
                    MemberIntakeKey(
                        client_id=item.client_id,
                        member_id=pk(member),
                        submitted_by_user_id=actor.user_id,
                        captured_at=item.captured_at,
                        capture_location=location,
                        created_at=datetime.now(UTC),
                    )
                )
                await db.flush()
        except AppError as error:
            results.append(
                BatchItemOut(
                    client_id=item.client_id,
                    status="error",
                    error_code=error.code,
                    error=error.detail or error.title,
                )
            )
            continue
        results.append(
            BatchItemOut(client_id=item.client_id, status="accepted", member_id=member.id)
        )
    await db.commit()
    return results


# --- imports ------------------------------------------------------------------------------------


async def queue_import(
    db: AsyncSession,
    storage: ObjectStorage,
    actor: Actor,
    *,
    filename: str,
    data: bytes,
    dry_run: bool,
    evidence_uri: str,
    default_level_id: uuid.UUID | None,
) -> MemberImportRun:
    extension = next((ext for ext in IMPORT_TYPES if filename.lower().endswith(ext)), None)
    if extension is None:
        raise BadRequestError("El archivo debe ser CSV o Excel (.xlsx).")
    if not data or len(data) > IMPORT_MAX_BYTES:
        raise BadRequestError("El archivo debe pesar entre 1 byte y 20 MB.")
    if default_level_id is not None:
        await catalog.get_level(db, default_level_id)
    key = ObjectStorage.new_key("peace_movement/imports", extension.lstrip("."))
    await storage.put(key, data, IMPORT_TYPES[extension])
    run = MemberImportRun(
        filename=filename[:200],
        storage_key=key,
        dry_run=dry_run,
        status=ImportStatus.QUEUED,
        evidence_uri=evidence_uri,
        default_level_id=default_level_id,
        created_by_user_id=actor.user_id,
    )
    db.add(run)
    await db.commit()
    return run


def _normalize(header: str) -> str:
    plain = unicodedata.normalize("NFKD", header).encode("ascii", "ignore").decode()
    return "_".join(plain.strip().lower().replace("-", " ").split())


def parse_rows(filename: str, data: bytes) -> Iterator[dict[str, str]]:
    """Rows as dicts with normalized headers (lowercase, no accents, underscores)."""
    if filename.lower().endswith(".xlsx"):
        sheet = load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
        if sheet is None:
            return
        rows = sheet.iter_rows(values_only=True)
        header = [_normalize(str(h or "")) for h in next(rows, ())]
        for values in rows:
            if any(v not in (None, "") for v in values):
                yield {
                    header[i]: "" if v is None else str(v).strip()
                    for i, v in enumerate(values)
                    if i < len(header)
                }
        return
    text_data = data.decode("utf-8-sig")
    dialect = csv.Sniffer().sniff(text_data[:4096], delimiters=",;\t|")
    reader = csv.reader(io.StringIO(text_data), dialect)
    header = [_normalize(h) for h in next(reader, [])]
    for values in reader:
        if any(v.strip() for v in values):
            yield {header[i]: v.strip() for i, v in enumerate(values) if i < len(header)}


async def _levels_by_name(db: AsyncSession) -> dict[str, uuid.UUID]:
    rows = (await db.execute(select(ParticipationLevel))).scalars()
    found: dict[str, uuid.UUID] = {}
    for level in rows:
        found[level.code] = pk(level)
        found[_normalize(level.name)] = pk(level)
    return found


async def _row_enrollment(
    db: AsyncSession,
    crypto: people.Crypto,
    row: dict[str, str],
    *,
    context: "_ImportContext",
    in_file_recruiter: bool,
) -> EnrollmentIn:
    """`in_file_recruiter`: in a dry run, the recruiter is another row of the file that was not
    written, so the row is validated without it (the dependency is checked apart)."""
    levels, default_level_id = context.level_names, context.run.default_level_id

    def need(name: str) -> str:
        value = row.get(name, "")
        if not value:
            raise BadRequestError(f"Falta la columna «{name}».")
        return value

    try:
        state_code, section_number = int(need("entidad")), int(need("seccion"))
    except ValueError:
        raise BadRequestError("«entidad» y «seccion» deben ser números.") from None
    section_id = await _section(db, state_code, section_number, context.sections)
    level_name = row.get("nivel", "")
    level_id = levels.get(_normalize(level_name)) if level_name else default_level_id
    if level_id is None:
        raise BadRequestError(f"Nivel desconocido: «{level_name}».")
    recruiter_id: uuid.UUID | None = None
    if code := row.get("codigo_reclutador"):
        recruiter_id = pk(await recruiter_by_code(db, code))
    elif in_file_recruiter:
        recruiter_id = None
    elif (recruiter_curp := row.get("curp_reclutador", "").upper()) in context.recruiters_by_curp:
        recruiter_id = context.recruiters_by_curp[recruiter_curp]
    elif recruiter_curp:
        recruiter_id = (
            await db.execute(
                select(col(Member.id))
                .join(Person, col(Person.id) == col(Member.person_id))
                .where(
                    col(Person.curp_hash) == crypto.curp_hash(recruiter_curp),
                    col(Member.status) == MemberStatus.ACTIVE,
                    col(Member.deleted_at).is_(None),
                )
            )
        ).scalar_one_or_none()
        if recruiter_id is None:
            raise BadRequestError("La CURP del reclutador no corresponde a un pacificador activo.")
        context.recruiters_by_curp[recruiter_curp] = recruiter_id
    contacts = []
    if mobile := row.get("celular"):
        contacts.append(ContactIn(contact_type="mobile", value=mobile, is_primary=True))
    if email := row.get("correo"):
        contacts.append(ContactIn(contact_type="email", value=email))
    origin = row.get("origen") or ("recruiter" if recruiter_id else "structure")
    if in_file_recruiter or (origin == "recruiter" and recruiter_id is None):
        origin = "structure" if in_file_recruiter else origin
    return EnrollmentIn.model_validate(
        {
            "person": PersonCreate(
                given_names=need("nombre"),
                paternal_surname=need("apellido_paterno"),
                maternal_surname=row.get("apellido_materno") or None,
                curp=need("curp"),
                contacts=contacts,
                address=AddressIn(
                    street=row.get("calle") or None,
                    exterior_number=row.get("numero_exterior") or None,
                    postal_code=row.get("codigo_postal") or None,
                    section_id=section_id,
                ),
            ),
            "level_id": level_id,
            "recruiter_member_id": recruiter_id,
            "origin": origin,
            "origin_detail": row.get("detalle_origen") or None,
            "consent": ConsentCapture(channel="paper", evidence_uri=context.run.evidence_uri),
        }
    )


async def _actor_of(db: AsyncSession, user_id: uuid.UUID) -> Actor:
    """The scope of the import permission (D-101): the run acts only where the user may import."""
    access = await load_access(db, user_id)
    geo = await resolve_scope(db, user_id, access, PeacePerm.MEMBER_IMPORT)
    return Actor(user_id=user_id, geo=geo)


async def process_next_import(
    sessions: async_sessionmaker[AsyncSession], storage: ObjectStorage, crypto: people.Crypto
) -> MemberImportRun | None:
    """Processes the oldest queued import (the scheduler calls it under the job lock)."""
    async with sessions() as db:
        run = (
            await db.execute(
                select(MemberImportRun)
                .where(col(MemberImportRun.status) == ImportStatus.QUEUED)
                .order_by(col(MemberImportRun.created_at))
                .limit(1)
                .with_for_update(skip_locked=True)
            )
        ).scalar_one_or_none()
        if run is None:
            return None
        run.status = ImportStatus.RUNNING
        run.started_at = datetime.now(UTC)
        await db.commit()
        run_id = pk(run)
    try:
        data = await storage.get(run.storage_key)
        rows = list(parse_rows(run.filename, data))
        if len(rows) > IMPORT_MAX_ROWS:
            raise BadRequestError(f"El archivo pasa de {IMPORT_MAX_ROWS:,} filas.")
        accepted, errors = await _import_rows(sessions, crypto, run, rows)
    except Exception as error:  # the run must end in a final state
        logger.exception("member_import_failed", run_id=str(run_id))
        async with sessions() as db:
            failed = await db.get(MemberImportRun, run_id)
            assert failed is not None  # noqa: S101
            failed.status = ImportStatus.FAILED
            failed.failure = (getattr(error, "detail", None) or str(error))[:500]
            failed.finished_at = datetime.now(UTC)
            await db.commit()
            return failed
    async with sessions() as db:
        done = await db.get(MemberImportRun, run_id)
        assert done is not None  # noqa: S101
        done.status = ImportStatus.DONE
        done.total_rows = len(rows)
        done.accepted_rows = accepted
        done.error_rows = errors
        done.finished_at = datetime.now(UTC)
        await db.commit()
        return done


@dataclass
class _ImportContext:
    run: MemberImportRun
    actor: Actor
    cache: members.RegisterCache
    level_names: dict[str, uuid.UUID]
    sections: dict[tuple[int, int], uuid.UUID] = field(default_factory=dict)
    recruiters_by_curp: dict[str, uuid.UUID] = field(default_factory=dict)


def _waves(rows: list[dict[str, str]]) -> tuple[list[list[int]], dict[int, int], set[int]]:
    """Orders the rows so a recruiter in the file is written before its recruits: wave 0 has no
    recruiter in the file, wave n depends on wave n-1. Returns (waves, row → recruiter row,
    rows in a recruitment cycle)."""
    by_curp = {row.get("curp", "").upper(): i for i, row in enumerate(rows) if row.get("curp")}
    parent: dict[int, int] = {}
    for i, row in enumerate(rows):
        recruiter = by_curp.get(row.get("curp_reclutador", "").upper())
        if recruiter is not None and recruiter != i:
            parent[i] = recruiter
    depth: dict[int, int] = {}
    cyclic: set[int] = set()
    for start in range(len(rows)):
        chain, node = [], start
        while node not in depth and node in parent and node not in chain:
            chain.append(node)
            node = parent[node]
        if node in chain:  # a cycle: none of its rows can be ordered
            cyclic.update(chain)
            for item in chain:
                depth[item] = -1
            continue
        base = depth.get(node, 0 if node not in parent else -1)
        if node not in depth:
            depth[node] = base
        for item in reversed(chain):
            base = -1 if base < 0 else base + 1
            depth[item] = base
    waves: list[list[int]] = []
    for i in range(len(rows)):
        level = depth.get(i, 0)
        if level < 0:
            cyclic.add(i)
            continue
        while len(waves) <= level:
            waves.append([])
        waves[level].append(i)
    return waves, parent, cyclic


async def _import_rows(
    sessions: async_sessionmaker[AsyncSession],
    crypto: people.Crypto,
    run: MemberImportRun,
    rows: list[dict[str, str]],
) -> tuple[int, int]:
    """Imports the rows in waves (recruiters first) and, inside a wave, in parallel chunks of
    `IMPORT_CHUNK` rows, each in its own transaction. Rows are audited in bulk, one entry per
    chunk, so parallel chunks do not queue on the audit chain lock (D-90, D-98). A dry run
    validates every row (recruiters in the file are checked as rows) and writes nothing."""
    async with sessions() as db:
        notice = await people.current_notice(db, members.NOTICE_CODE)
        if notice is None:
            raise members.NoticeUnavailableError("No hay un aviso del Movimiento de Paz vigente.")
        context = _ImportContext(
            run=run,
            actor=await _actor_of(db, run.created_by_user_id),
            cache=members.RegisterCache(
                notice=notice,
                settings=await catalog.get_settings(db),
                levels={pk(level): level for level in await catalog.list_levels(db)},
            ),
            level_names=await _levels_by_name(db),
        )
        await db.commit()
    waves, parent, cyclic = _waves(rows)
    failed: dict[int, MemberImportError] = {
        i: MemberImportError(
            run_id=pk(run),
            row_number=i + 2,
            code="recruiter-cycle",
            detail="La fila forma un ciclo de reclutadores dentro del archivo.",
        )
        for i in cyclic
    }
    if run.dry_run:  # no row is written, so no wave waits for another
        waves = [[i for wave in waves for i in wave]]
    semaphore = asyncio.Semaphore(IMPORT_WORKERS)
    accepted = 0
    for wave in waves:
        pending = [i for i in wave if parent.get(i) not in failed]
        for i in wave:
            if parent.get(i) in failed and i not in failed:
                failed[i] = MemberImportError(
                    run_id=pk(run),
                    row_number=i + 2,
                    code="recruiter-row-failed",
                    detail=f"Su reclutador (fila {parent[i] + 2}) tiene errores.",
                )
        chunks = [pending[k : k + IMPORT_CHUNK] for k in range(0, len(pending), IMPORT_CHUNK)]

        async def guarded(chunk: list[int]) -> tuple[int, dict[int, MemberImportError]]:
            async with semaphore:
                return await _import_chunk(sessions, crypto, context, rows, chunk, parent)

        for count, errors in await asyncio.gather(*(guarded(chunk) for chunk in chunks)):
            accepted += count
            failed.update(errors)
    if run.dry_run:  # a row whose in-file recruiter failed also fails
        for i in sorted(parent):
            if parent[i] in failed and i not in failed:
                failed[i] = MemberImportError(
                    run_id=pk(run),
                    row_number=i + 2,
                    code="recruiter-row-failed",
                    detail=f"Su reclutador (fila {parent[i] + 2}) tiene errores.",
                )
                accepted -= 1
    if failed:
        async with sessions() as db:
            db.add_all([failed[i] for i in sorted(failed)])
            await db.commit()
    return accepted, len(failed)


async def _import_chunk(  # noqa: PLR0917
    sessions: async_sessionmaker[AsyncSession],
    crypto: people.Crypto,
    context: _ImportContext,
    rows: list[dict[str, str]],
    chunk: list[int],
    parent: dict[int, int],
) -> tuple[int, dict[int, MemberImportError]]:
    run = context.run
    errors: dict[int, MemberImportError] = {}
    created: list[Member] = []
    async with sessions() as db:
        db.sync_session.info["audit_skip_tables"] = BULK_AUDITED
        await db.execute(text("SET LOCAL statement_timeout = '10min'"))
        for i in chunk:
            try:
                async with db.begin_nested():
                    body = await _row_enrollment(
                        db,
                        crypto,
                        rows[i],
                        context=context,
                        in_file_recruiter=run.dry_run and i in parent,
                    )
                    created.append(
                        await members.enroll(
                            db,
                            crypto,
                            context.actor,
                            body,
                            channel=EnrollmentChannel.IMPORT,
                            status=MemberStatus.ACTIVE,
                            commit=False,
                            cache=context.cache,
                        )
                    )
            except (AppError, ValidationError) as error:
                errors[i] = _error_row(pk(run), i + 2, error)
        if run.dry_run:
            await db.rollback()  # validate only: nothing of the rows is written
        else:
            if created:
                await record_bulk(
                    db,
                    action="member_import",
                    entity_table="peace_movement.members",
                    entity_ids=[pk(member) for member in created],
                    details={
                        "run_id": str(run.id),
                        "person_ids": [str(member.person_id) for member in created],
                    },
                )
            await db.commit()
    return len(created), errors


def _error_row(run_id: uuid.UUID, row_number: int, error: Exception) -> MemberImportError:
    if isinstance(error, AppError):
        code, detail = error.code, error.detail or error.title
    elif isinstance(error, ValidationError) and error.errors():
        first = error.errors()[0]
        code = "invalid-row"
        detail = f"{'.'.join(str(part) for part in first['loc'])}: {first['msg']}"
    else:
        code, detail = "invalid-row", str(error)
    return MemberImportError(run_id=run_id, row_number=row_number, code=code, detail=detail[:500])


async def list_runs(
    db: AsyncSession, actor: Actor, params: PageParams
) -> CursorPage[MemberImportRun]:
    statement = select(MemberImportRun).where(col(MemberImportRun.deleted_at).is_(None))
    if not actor.geo.unrestricted:
        statement = statement.where(col(MemberImportRun.created_by_user_id) == actor.user_id)
    sort = parse_sort(
        params.sort,
        allowed={"created_at": col(MemberImportRun.created_at)},
        tiebreaker=col(MemberImportRun.id),
        default="-created_at",
    )
    page: CursorPage[MemberImportRun] = await paginate(
        db, statement, sort=sort, limit=params.limit, cursor=params.cursor
    )
    return page


async def get_run(db: AsyncSession, actor: Actor, run_id: uuid.UUID) -> MemberImportRun:
    run = await db.get(MemberImportRun, run_id)
    if run is None or run.deleted_at is not None:
        raise NotFoundError("Importación no encontrada.")
    if not actor.geo.unrestricted and run.created_by_user_id != actor.user_id:
        raise NotFoundError("Importación no encontrada.")
    return run


async def run_errors(
    db: AsyncSession, actor: Actor, run_id: uuid.UUID, params: PageParams
) -> CursorPage[MemberImportError]:
    await get_run(db, actor, run_id)
    statement = select(MemberImportError).where(col(MemberImportError.run_id) == run_id)
    sort = parse_sort(
        params.sort,
        allowed={"row_number": col(MemberImportError.row_number)},
        tiebreaker=col(MemberImportError.id),
        default="row_number",
    )
    page: CursorPage[MemberImportError] = await paginate(
        db, statement, sort=sort, limit=params.limit, cursor=params.cursor
    )
    return page
