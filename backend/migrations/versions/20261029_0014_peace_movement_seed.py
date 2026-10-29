"""peace_movement: permissions, participation levels, national goals and settings (D-92)

Levels and their national recruitment goals come from the brief (docs/modules/peace-movement.md):
Pacificador 1, Promotor de la Paz 10, Mensajero de Paz 50, Constructor de Paz 100 and Embajador
de Paz 500 (plus 5 consolidated houses). A Peace House consolidates with 100 members. Admins
adjust goals per state from the API; history is kept.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-29
"""

from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_DATE = date(2026, 1, 1)

# code, name, rank, recruit goal, house goal
LEVELS = [
    ("pacifier", "Pacificador", 1, 1, None),
    ("peace_promoter", "Promotor de la Paz", 2, 10, None),
    ("peace_messenger", "Mensajero de Paz", 3, 50, None),
    ("peace_builder", "Constructor de Paz", 4, 100, None),
    ("peace_ambassador", "Embajador de Paz", 5, 500, 5),
]
HOUSE_MEMBER_GOAL = 100

PERMISSIONS = [
    ("peace_movement.member.read", "read", "Buscar y ver pacificadores y su red"),
    ("peace_movement.member.write", "write", "Inscribir pacificadores y cambiar su nivel"),
    (
        "peace_movement.member.validate",
        "validate",
        "Validar o rechazar inscripciones y registrar salidas del movimiento",
    ),
    ("peace_movement.member.reassign", "reassign", "Cambiar el reclutador de un pacificador"),
    ("peace_movement.member.import", "import", "Importar listas de pacificadores"),
    ("peace_movement.house.read", "house_read", "Ver Casas de Paz, integrantes y reuniones"),
    ("peace_movement.house.write", "house_write", "Abrir, editar y cerrar Casas de Paz"),
    (
        "peace_movement.house.reassign_credit",
        "house_reassign_credit",
        "Reasignar el crédito de una Casa de Paz",
    ),
    ("peace_movement.stats.read", "stats_read", "Estadísticas y reportes del movimiento"),
    (
        "peace_movement.goal.manage",
        "goal_manage",
        "Niveles, metas, coordinadores de zona y configuración del movimiento",
    ),
]

READ = ["peace_movement.member.read", "peace_movement.house.read"]
CAPTURE = ["peace_movement.member.write", "peace_movement.house.write"]
COORDINATION = [
    "peace_movement.member.validate",
    "peace_movement.member.reassign",
    "peace_movement.member.import",
    "peace_movement.house.reassign_credit",
    "peace_movement.stats.read",
]
GRANTS = {
    "admin": [*READ, *CAPTURE, *COORDINATION, "peace_movement.goal.manage"],
    "coordinator": [*READ, *CAPTURE, *COORDINATION],
    "capturist": [*READ, *CAPTURE],
    "viewer": [*READ, "peace_movement.stats.read"],
}


def upgrade() -> None:
    bind = op.get_bind()
    for code, action, description in PERMISSIONS:
        bind.execute(
            sa.text(
                "INSERT INTO identity.permissions (code, module, action, description) "
                "VALUES (:code, 'peace_movement', :action, :description)"
            ),
            {"code": code, "action": action, "description": description},
        )
    for role, codes in GRANTS.items():
        for code in codes:
            bind.execute(
                sa.text(
                    "INSERT INTO identity.role_permissions (role_id, permission_id) "
                    "SELECT r.id, p.id FROM identity.roles r, identity.permissions p "
                    "WHERE r.code = :role AND p.code = :code"
                ),
                {"role": role, "code": code},
            )
    for code, name, rank, recruit_goal, house_goal in LEVELS:
        bind.execute(
            sa.text(
                "WITH level AS (INSERT INTO peace_movement.participation_levels "
                "(code, name, rank, sort_order) VALUES (:code, :name, :rank, :rank) RETURNING id) "
                "INSERT INTO peace_movement.level_goals (level_id, recruit_goal, house_goal, "
                "valid_from) SELECT id, :recruit_goal, :house_goal, :valid_from "
                "FROM level"
            ),
            {
                "code": code,
                "name": name,
                "rank": rank,
                "recruit_goal": recruit_goal,
                "house_goal": house_goal,
                "valid_from": SEED_DATE,
            },
        )
    bind.execute(
        sa.text(
            "INSERT INTO peace_movement.house_goals (member_goal, valid_from) "
            "VALUES (:goal, :valid_from)"
        ),
        {"goal": HOUSE_MEMBER_GOAL, "valid_from": SEED_DATE},
    )
    bind.execute(
        sa.text(
            "INSERT INTO peace_movement.settings (traffic_light_yellow_pct, "
            "traffic_light_green_pct, depth_alert_threshold) VALUES (50, 100, 50)"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM peace_movement.settings"))
    bind.execute(sa.text("DELETE FROM peace_movement.house_goals"))
    bind.execute(sa.text("DELETE FROM peace_movement.level_goals"))
    bind.execute(sa.text("DELETE FROM peace_movement.participation_levels"))
    bind.execute(
        sa.text("DELETE FROM identity.permissions WHERE code = ANY(:codes)"),
        {"codes": [code for code, *_ in PERMISSIONS]},
    )
