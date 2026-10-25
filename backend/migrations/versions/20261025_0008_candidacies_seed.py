"""candidacies: seed office types (D-22), validation rules (D-28), the PAZ party and the
people/candidacies permissions with their role grants (D-33)

Self-contained on purpose (no application imports). Office types and rules are data: new
offices are added from the panel/API without migrations.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-25
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# code, name, election level, geographic level, principle, nomination kind, default positions, order
OFFICE_TYPES = [
    ("municipal_president", "Presidencia municipal", "local", "municipality", "mr", "slate", 1, 10),
    ("syndic", "Sindicatura", "local", "municipality", "mr", "single", 1, 11),
    (
        "councilor_mr",
        "Regiduría de mayoría relativa",
        "local",
        "municipality",
        "mr",
        "member",
        None,
        12,
    ),
    (
        "councilor_rp",
        "Regiduría de representación proporcional",
        "local",
        "municipality",
        "rp",
        "member",
        None,
        13,
    ),
    ("mayor", "Alcaldía", "local", "municipality", "mr", "slate", 1, 14),
    ("council_member", "Concejalía", "local", "municipality", "mr", "member", None, 15),
    (
        "local_deputy_mr",
        "Diputación local de mayoría relativa",
        "local",
        "local_district",
        "mr",
        "single",
        1,
        20,
    ),
    (
        "local_deputy_rp",
        "Diputación local de representación proporcional",
        "local",
        "state",
        "rp",
        "list",
        None,
        21,
    ),
    ("governor", "Gubernatura", "local", "state", "mr", "single", 1, 30),
    (
        "federal_deputy_mr",
        "Diputación federal de mayoría relativa",
        "federal",
        "federal_district",
        "mr",
        "single",
        1,
        40,
    ),
    (
        "federal_deputy_rp",
        "Diputación federal de representación proporcional",
        "federal",
        "electoral_region",
        "rp",
        "list",
        40,
        41,
    ),
    ("senator_mr", "Senaduría de mayoría relativa", "federal", "state", "mr", "list", 2, 50),
    (
        "senator_rp",
        "Senaduría de representación proporcional",
        "federal",
        "national",
        "rp",
        "list",
        32,
        51,
    ),
    ("president", "Presidencia de la República", "federal", "national", "mr", "single", 1, 60),
]

RULES = [
    (
        "unique_person_in_process",
        "Persona no duplicada en el proceso",
        "Una persona no puede integrar más de una fórmula activa (propietaria o suplente) en el mismo proceso.",
        {},
    ),
    (
        "substitute_same_sex",
        "Suplente del mismo sexo",
        "La persona suplente debe ser del mismo sexo que la propietaria.",
        {"allow_male_owner_female_substitute": False},
    ),
    (
        "list_alternation",
        "Alternancia en listas y planillas",
        "En cada cargo de una lista o planilla, las posiciones consecutivas alternan el sexo de la persona propietaria.",
        {},
    ),
    (
        "gender_parity",
        "Paridad de género",
        "Proporción mínima de mujeres entre las personas propietarias que encabezan las postulaciones de un cargo en el proceso.",
        {"min_female_ratio": 0.5},
    ),
]

PERMISSIONS = [
    ("people.person.read", "people", "read", "Consultar personas"),
    ("people.person.write", "people", "write", "Registrar y editar personas"),
    (
        "people.person.read_sensitive",
        "people",
        "read_sensitive",
        "Ver CURP, teléfonos y domicilios completos",
    ),
    ("people.person.delete", "people", "delete", "Eliminar personas (derechos ARCO)"),
    ("candidacies.read", "candidacies", "read", "Consultar procesos, postulaciones y fórmulas"),
    (
        "candidacies.catalog.manage",
        "candidacies",
        "manage",
        "Administrar partidos y tipos de cargo",
    ),
    (
        "candidacies.process.manage",
        "candidacies",
        "manage",
        "Administrar procesos, su configuración, coaliciones y reglas",
    ),
    ("candidacies.nomination.write", "candidacies", "write", "Capturar postulaciones y fórmulas"),
    (
        "candidacies.nomination.approve",
        "candidacies",
        "approve",
        "Aprobar, cancelar y sustituir candidaturas",
    ),
    (
        "candidacies.rule.override",
        "candidacies",
        "override",
        "Aceptar violaciones de reglas con justificación",
    ),
]

GRANTS = {
    "admin": [
        "people.person.read",
        "people.person.write",
        "people.person.read_sensitive",
        "people.person.delete",
        "candidacies.read",
        "candidacies.catalog.manage",
        "candidacies.process.manage",
    ],
    "coordinator": [
        "people.person.read",
        "people.person.write",
        "people.person.read_sensitive",
        "candidacies.read",
        "candidacies.nomination.write",
        "candidacies.nomination.approve",
        "candidacies.rule.override",
    ],
    "capturist": [
        "people.person.read",
        "people.person.write",
        "candidacies.read",
        "candidacies.nomination.write",
    ],
    "viewer": ["people.person.read", "candidacies.read"],
}


def upgrade() -> None:
    bind = op.get_bind()
    for code, name, level, geo, principle, kind, positions, order in OFFICE_TYPES:
        bind.execute(
            sa.text(
                "INSERT INTO candidacies.office_types (code, name, election_level, geographic_level, "
                "principle, nomination_kind, default_positions, sort_order) "
                "VALUES (:code, :name, :level, :geo, :principle, :kind, :positions, :order)"
            ),
            {
                "code": code,
                "name": name,
                "level": level,
                "geo": geo,
                "principle": principle,
                "kind": kind,
                "positions": positions,
                "order": order,
            },
        )
    for code, name, description, params in RULES:
        bind.execute(
            sa.text(
                "INSERT INTO candidacies.validation_rules (code, name, description, default_params) "
                "VALUES (:code, :name, :description, CAST(:params AS jsonb))"
            ),
            {"code": code, "name": name, "description": description, "params": json.dumps(params)},
        )
    bind.execute(
        sa.text(
            "INSERT INTO candidacies.parties (acronym, name, is_own_party) VALUES ('PAZ', 'PAZ', true)"
        )
    )
    for code, module, action, description in PERMISSIONS:
        bind.execute(
            sa.text(
                "INSERT INTO identity.permissions (code, module, action, description) "
                "VALUES (:code, :module, :action, :description)"
            ),
            {"code": code, "module": module, "action": action, "description": description},
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


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM identity.permissions WHERE code = ANY(:codes)"),
        {"codes": [code for code, *_ in PERMISSIONS]},
    )
    bind.execute(sa.text("DELETE FROM candidacies.parties WHERE acronym = 'PAZ'"))
    bind.execute(
        sa.text("DELETE FROM candidacies.validation_rules WHERE code = ANY(:codes)"),
        {"codes": [code for code, *_ in RULES]},
    )
    bind.execute(
        sa.text("DELETE FROM candidacies.office_types WHERE code = ANY(:codes)"),
        {"codes": [code for code, *_ in OFFICE_TYPES]},
    )
