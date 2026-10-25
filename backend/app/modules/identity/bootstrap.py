"""First-run bootstrap: create the initial superadmin from the CLI."""

import uuid

from app.core.audit import record_audit
from app.core.config import Settings
from app.core.context import RequestContext, set_context
from app.core.db.session import build_engine, build_sessionmaker
from app.core.errors import ConflictError
from app.modules.identity import repository as repo
from app.modules.identity.models import User, UserRole, UserStatus
from app.modules.identity.security.passwords import Passwords
from app.modules.identity.services.access import utcnow


async def create_superadmin(
    settings: Settings, email: str, full_name: str, password: str
) -> uuid.UUID:
    set_context(RequestContext(request_id="cli-create-superadmin", user_agent="paz-cli"))
    passwords = Passwords(settings)
    passwords.validate(password, email=email)
    engine = build_engine(settings)
    try:
        async with build_sessionmaker(engine)() as db:
            if await repo.user_by_email(db, email) is not None:
                raise ConflictError("Ya existe un usuario con ese correo.")
            role = await repo.role_by_code(db, "superadmin")
            if role is None or role.id is None:
                raise RuntimeError("El rol superadmin no existe; ejecuta las migraciones.")
            user = User(
                email=email,
                full_name=full_name,
                password_hash=passwords.hash(password),
                status=UserStatus.ACTIVE,
                password_changed_at=utcnow(),
            )
            db.add(user)
            await db.flush()
            assert user.id is not None  # noqa: S101
            db.add(UserRole(user_id=user.id, role_id=role.id))
            await record_audit(
                db,
                action="superadmin_bootstrapped",
                entity_table="identity.users",
                entity_id=str(user.id),
            )
            await db.commit()
            return user.id
    finally:
        await engine.dispose()
