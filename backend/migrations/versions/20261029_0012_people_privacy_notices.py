"""people: privacy notice catalog and consents on a catalogued notice (D-82)

- `people.privacy_notices`: each version of a notice (`general`, `peace_movement`), with the
  SHA-256 of its text; one current version per code.
- `privacy_consents` gains `notice_id`, `notice_code` (existing rows: `general`) and
  `notice_text_sha256`, and the channels of the Peace Movement (`referral_link`, `import`,
  `field_app`).
- Permission `people.notice.manage` (publish notices), granted to `admin`.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_CHANNELS = "channel IN ('panel', 'paper', 'web')"
NEW_CHANNELS = "channel IN ('panel', 'paper', 'web', 'referral_link', 'import', 'field_app')"
PERMISSION = ("people.notice.manage", "people", "notice_manage", "Publicar avisos de privacidad")


def upgrade() -> None:
    op.create_table(
        "privacy_notices",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("code", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column("version", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("body_sha256", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("is_sample", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_privacy_notices")),
        schema="people",
    )
    op.create_index(
        "uq_privacy_notices_code_version",
        "privacy_notices",
        ["code", "version"],
        unique=True,
        schema="people",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_privacy_notices_current",
        "privacy_notices",
        ["code"],
        unique=True,
        schema="people",
        postgresql_where=sa.text("valid_to IS NULL AND deleted_at IS NULL"),
    )
    op.add_column(
        "privacy_consents", sa.Column("notice_id", sa.Uuid(), nullable=True), schema="people"
    )
    op.add_column(
        "privacy_consents",
        sa.Column(
            "notice_code",
            sqlmodel.sql.sqltypes.AutoString(length=50),
            server_default="general",
            nullable=False,
        ),
        schema="people",
    )
    op.add_column(
        "privacy_consents",
        sa.Column("notice_text_sha256", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
        schema="people",
    )
    op.create_foreign_key(
        op.f("fk_privacy_consents_notice_id__privacy_notices"),
        "privacy_consents",
        "privacy_notices",
        ["notice_id"],
        ["id"],
        source_schema="people",
        referent_schema="people",
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        op.f("ck_privacy_consents_channel"), "privacy_consents", schema="people", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_privacy_consents_channel"), "privacy_consents", NEW_CHANNELS, schema="people"
    )
    bind = op.get_bind()
    code, module, action, description = PERMISSION
    bind.execute(
        sa.text(
            "INSERT INTO identity.permissions (code, module, action, description) "
            "VALUES (:code, :module, :action, :description)"
        ),
        {"code": code, "module": module, "action": action, "description": description},
    )
    bind.execute(
        sa.text(
            "INSERT INTO identity.role_permissions (role_id, permission_id) "
            "SELECT r.id, p.id FROM identity.roles r, identity.permissions p "
            "WHERE r.code = 'admin' AND p.code = :code"
        ),
        {"code": code},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM identity.permissions WHERE code = :code"), {"code": PERMISSION[0]}
    )
    op.execute(
        "DELETE FROM people.privacy_consents WHERE channel IN ('referral_link', 'import', "
        "'field_app')"
    )
    op.drop_constraint(
        op.f("ck_privacy_consents_channel"), "privacy_consents", schema="people", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_privacy_consents_channel"), "privacy_consents", OLD_CHANNELS, schema="people"
    )
    op.drop_constraint(
        op.f("fk_privacy_consents_notice_id__privacy_notices"),
        "privacy_consents",
        schema="people",
        type_="foreignkey",
    )
    op.drop_column("privacy_consents", "notice_text_sha256", schema="people")
    op.drop_column("privacy_consents", "notice_code", schema="people")
    op.drop_column("privacy_consents", "notice_id", schema="people")
    op.drop_index(
        "uq_privacy_notices_current",
        table_name="privacy_notices",
        schema="people",
        postgresql_where=sa.text("valid_to IS NULL AND deleted_at IS NULL"),
    )
    op.drop_index(
        "uq_privacy_notices_code_version",
        table_name="privacy_notices",
        schema="people",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("privacy_notices", schema="people")
