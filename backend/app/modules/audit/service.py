"""Who can read which audit entries (D-93).

Audit entries are generic (any table), so the scope is resolved by actor, not by entity: a user
with a limited scope reads the entries made by themselves or by users they can manage (scope
inside theirs, the user-administration rule). Entries without actor (cron, imports) and those
of superadmins are only visible to users without restriction.
"""

from sqlalchemy import ColumnElement, Table, or_, select
from sqlmodel import col

from app.modules.identity.models import Role, User, UserRole
from app.modules.identity.services.scopes import GeoScope, manageable_users_filter


def readable_entries(geo: GeoScope, table: Table) -> ColumnElement[bool] | None:
    """SQL filter over `audit_log` or `access_log`; None when the reader has no restriction."""
    if geo.unrestricted:
        return None
    superadmins = (
        select(col(UserRole.user_id))
        .join(Role, col(Role.id) == col(UserRole.role_id))
        .where(col(Role.grants_all).is_(True), col(Role.deleted_at).is_(None))
    )
    manageable = manageable_users_filter(geo, col(User.id))
    managed = select(col(User.id)).where(col(User.id).not_in(superadmins))
    if manageable is not None:
        managed = managed.where(manageable)
    actor = table.c.actor_user_id
    return or_(actor == geo.user_id, actor.in_(managed))
