"""/public/peace-movement — enrollment through a member's link or QR, without a session
(D-86). Everything here is rate limited and protected by a proof of work."""

from typing import Annotated

from fastapi import APIRouter, Path, Request, status

from app.core import pow as proof
from app.core.context import get_context
from app.core.db.session import SessionDep
from app.core.redis import RedisDep
from app.modules.identity.container import ServicesDep
from app.modules.peace_movement import catalog, intake
from app.modules.peace_movement.schemas import (
    ChallengeOut,
    NoticeView,
    PublicEnrollmentIn,
    PublicEnrollmentOut,
    PublicFormOut,
    PublicLevelOut,
)
from app.modules.people.views import CryptoDep

router = APIRouter(prefix="/public/peace-movement", tags=["peace-movement-public"])

ReferralCode = Annotated[str, Path(min_length=8, max_length=32)]


def _key(request: Request) -> bytes:
    return proof.secret_key(request.app.state.settings)


@router.get(
    "/enroll/{referral_code}",
    operation_id="getPublicEnrollmentForm",
    summary="Formulario público de inscripción: aviso, niveles y verificación anti-bots",
)
async def get_form(request: Request, db: SessionDep, referral_code: ReferralCode) -> PublicFormOut:
    notice, levels, challenge = await intake.public_form(db, _key(request), referral_code)
    goals = {
        goal.level_id: goal.recruit_goal
        for goal in await catalog.list_level_goals(db)
        if goal.state_id is None
    }
    return PublicFormOut(
        notice=NoticeView.model_validate(notice, from_attributes=True),
        levels=[
            PublicLevelOut(id=level.id, name=level.name, recruit_goal=goals.get(level.id))  # type: ignore[arg-type]
            for level in levels
        ],
        challenge=ChallengeOut(
            algorithm=challenge.algorithm,
            challenge=challenge.challenge,
            salt=challenge.salt,
            signature=challenge.signature,
            max_number=challenge.max_number,
        ),
    )


@router.post(
    "/enroll",
    operation_id="publicEnroll",
    summary="Inscripción pública (queda pendiente de validar)",
    status_code=status.HTTP_202_ACCEPTED,
)
async def enroll(  # noqa: PLR0917
    request: Request,
    db: SessionDep,
    redis: RedisDep,
    services: ServicesDep,
    crypto: CryptoDep,
    body: PublicEnrollmentIn,
) -> PublicEnrollmentOut:
    await intake.public_enroll(
        db,
        crypto,
        redis,
        services.rate_limiter,
        _key(request),
        body,
        client_ip=get_context().client_ip,
    )
    return PublicEnrollmentOut()
