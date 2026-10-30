"""party_structure: statutory catalog of bodies and positions, installed bodies (phase 1)

- Catalog tables (`body_types`, `position_types`, `position_derivations`,
  `position_incompatibilities`, `coordination_position_types`) and `bodies`.
- Seed transcribed from docs/reference/cargos_paz.md (D-105, D-107): every body and position
  with its statutory basis, electing body and term. «Demás cargos que se creen» are not seeded:
  the catalog is editable. Incompatibilities start empty (D-105).
- National bodies and the bodies of the 32 states are seeded installed; district and municipal
  bodies exist only once installed.
- Permissions `party_structure.*` and the base roles «Dirigente territorial» and
  «Coordinador territorial» (D-105), both with TOTP.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-30 21:49:01.536156+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

from migrations.helpers import app_role, if_role_exists

revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- seed transcribed from docs/reference/cargos_paz.md ------------------------------------------

CN = "Congreso Nacional"
CE = "Congreso Estatal o de la Ciudad de México"
CDIR = "Consejo Directivo Nacional"
PRES = "Presidencia del Consejo Directivo Nacional"
LEADER = "territorial_leader"

# code, name, territorial level, requires installation, statutory basis
BODY_TYPES = [
    (
        "national_board",
        "Consejo Directivo Nacional",
        "national",
        False,
        "Arts. 17, 22, 30, 32, 41, 118, 122, 123 y Séptimo Transitorio",
    ),
    (
        "national_committee",
        "Comité Directivo Nacional",
        "national",
        False,
        "Arts. 17, 22, 30, 32, 41, 118, 122, 123 y Séptimo Transitorio",
    ),
    ("national_political_commission", "Comisión Política Nacional", "national", False, "Art. 45"),
    ("national_vigilance_committee", "Comité Nacional de Vigilancia", "national", False, "Art. 49"),
    (
        "national_honor_justice_commission",
        "Comisión Nacional de Honor y Justicia",
        "national",
        False,
        "Art. 58",
    ),
    ("national_electoral_commission", "Comisión Nacional Electoral", "national", False, "Art. 66"),
    (
        "national_presidium",
        "Mesa Directiva (Presídium) del Congreso Nacional",
        "national",
        False,
        "Art. 23 fracc. III",
    ),
    (
        "national_coordinations",
        "Coordinaciones Nacionales",
        "national",
        False,
        "Arts. 19, 30, 32, 33, 41, 43 y 45",
    ),
    (
        "special_coordinations",
        "Coordinaciones Especiales de la Presidencia del Consejo Directivo",
        "national",
        False,
        "Art. 33 fracc. XX",
    ),
    (
        "causes_coordinations",
        "Coordinaciones Nacionales de Causas y Movimientos Sociales",
        "national",
        False,
        "Arts. 33 fracc. V y 94 al 106",
    ),
    (
        "state_board",
        "Consejo Directivo Estatal",
        "state",
        False,
        "Arts. 22 fracc. III, 37 fracc. XXVII, 70 fracc. IV, 81 y 125",
    ),
    (
        "state_committee",
        "Comité Directivo Estatal o de la Ciudad de México",
        "state",
        False,
        "Arts. 22 fracc. III, 37 fracc. XXVII, 70 fracc. IV, 81 y 125",
    ),
    (
        "state_political_commission",
        "Comisión Política Estatal o de la Ciudad de México",
        "state",
        False,
        "Art. 77",
    ),
    (
        "state_presidium",
        "Mesa Directiva (Presídium) del Congreso Estatal o de la Ciudad de México",
        "state",
        False,
        "Art. 72 fracc. IV",
    ),
    (
        "state_coordinations",
        "Coordinaciones Estatales",
        "state",
        False,
        "Arts. 32 fracc. VIII, 69 fracc. V y VI, 77 fracc. VI y 81 fracc. VII",
    ),
    (
        "district_committee",
        "Comité Directivo Distrital",
        "district",
        True,
        "Arts. 18 fracc. X, 70 fracc. V, 85, 86 y 126",
    ),
    (
        "municipal_committee",
        "Comité Directivo Municipal o de Alcaldía",
        "municipal",
        True,
        "Arts. 18 fracc. XI, 70 fracc. V, 88, 89 y 126",
    ),
]

# body type, code, name, electing body, term years, statutory basis; options:
# scope ("circumscription"), months, max_terms, derived (list of source codes)
P = dict
POSITIONS = [
    # 1.1 A. Consejo Directivo Nacional
    P(
        body="national_board",
        code="cdn_president",
        name="Presidencia del Consejo Directivo",
        elect=CN,
        years=3,
    ),
    P(
        body="national_board",
        code="cdn_sg_political_relations",
        name="Secretaría General de Relaciones Políticas",
        elect=CN,
        years=3,
    ),
    P(
        body="national_board",
        code="cdn_sg_electoral_strategy",
        name="Secretaría General de Estrategia Electoral",
        elect=CN,
        years=3,
    ),
    # Secretarías y Direcciones del Comité Directivo Nacional
    P(
        body="national_committee",
        code="cdn_administration_finance",
        name="Secretaría de Administración y Finanzas",
        elect=CN,
        years=3,
    ),
    P(body="national_committee", code="cdn_legal", name="Secretaría Jurídica", elect=CN, years=3),
    P(
        body="national_committee",
        code="cdn_strategy_communication",
        name="Secretaría de Estrategia y Comunicación Política",
        elect=CN,
        years=3,
    ),
    P(
        body="national_committee",
        code="cdn_causes",
        name="Secretaría de Causas y Movimientos Sociales",
        elect=CN,
        years=3,
    ),
    P(
        body="national_committee",
        code="cdn_circumscription_secretary",
        name="Secretaría de Circunscripción",
        elect=CN,
        years=3,
        scope="circumscription",
        basis="Arts. 30, 36, 42, 70 y 83",
    ),
    # Secretarías y Direcciones Operativas Dependientes
    P(
        body="national_committee",
        code="cdn_organization",
        name="Secretaría de Organización",
        elect=CDIR,
        basis="Arts. 17 y 32",
    ),
    P(
        body="national_committee",
        code="cdn_territorial_operation",
        name="Secretaría de Operación Política Territorial",
        elect=CDIR,
        basis="Art. 32",
    ),
    P(
        body="national_committee",
        code="cdn_peace_foundation",
        name="Dirección de la Fundación de Promoción de la Cultura de la Paz",
        elect="Coordinación Nacional de Capacitación, Investigación y Promoción de la Cultura de la Paz",
        basis="Art. 41",
    ),
    # Integrantes del CDN con voz y voto (1.2 A)
    P(
        body="national_committee",
        code="national_training_coordination",
        name="Coordinación Nacional de Capacitación, Investigación y Promoción de la Cultura de la Paz",
        elect=CN,
        years=3,
        basis="Art. 30 fracc. VI y 41",
    ),
    P(
        body="national_committee",
        code="national_transparency_coordination",
        name="Coordinación de la Unidad de Transparencia",
        elect=CN,
        years=3,
        basis="Art. 30 fracc. VIII y 43",
    ),
    # 1.1 B. Órganos colegiados nacionales
    P(
        body="national_political_commission",
        code="cpn_president",
        name="Presidencia de la Comisión Política Nacional",
        elect=CN,
        years=3,
    ),
    P(
        body="national_political_commission",
        code="cpn_technical_secretary",
        name="Secretaría Técnica de la Comisión Política Nacional",
        elect=CN,
        years=3,
    ),
    P(
        body="national_vigilance_committee",
        code="cnv_president",
        name="Presidencia del Comité Nacional de Vigilancia",
        elect=CN,
        years=3,
    ),
    P(
        body="national_vigilance_committee",
        code="cnv_vice_president",
        name="Vicepresidencia del Comité Nacional de Vigilancia",
        elect=CN,
        years=3,
    ),
    P(
        body="national_vigilance_committee",
        code="cnv_agreements_secretary",
        name="Secretaría de Acuerdos del Comité Nacional de Vigilancia",
        elect=CN,
        years=3,
    ),
    P(
        body="national_honor_justice_commission",
        code="cnhj_president",
        name="Presidencia de la Comisión Nacional de Honor y Justicia",
        elect=CN,
        years=3,
    ),
    P(
        body="national_honor_justice_commission",
        code="cnhj_vice_president",
        name="Vicepresidencia de la Comisión Nacional de Honor y Justicia",
        elect=CN,
        years=3,
    ),
    P(
        body="national_honor_justice_commission",
        code="cnhj_agreements_secretary",
        name="Secretaría de Acuerdos de la Comisión Nacional de Honor y Justicia",
        elect=CN,
        years=3,
    ),
    P(
        body="national_electoral_commission",
        code="cne_president",
        name="Presidencia de la Comisión Nacional Electoral",
        elect=CN,
        years=3,
    ),
    P(
        body="national_electoral_commission",
        code="cne_vice_president",
        name="Vicepresidencia de la Comisión Nacional Electoral",
        elect=CN,
        years=3,
    ),
    P(
        body="national_electoral_commission",
        code="cne_technical_secretary",
        name="Secretaría Técnica de la Comisión Nacional Electoral",
        elect=CN,
        years=3,
    ),
    # 1.1 C. Presídium del Congreso Nacional (derived)
    P(
        body="national_presidium",
        code="np_president",
        name="Presidencia del Presídium",
        derived=["cdn_president"],
    ),
    P(
        body="national_presidium",
        code="np_vice_president",
        name="Vicepresidencia del Presídium",
        derived=["cdn_sg_political_relations", "cdn_sg_electoral_strategy"],
    ),
    P(
        body="national_presidium",
        code="np_secretary",
        name="Secretaría del Presídium",
        derived=["cpn_president"],
    ),
    # 1.2 A. Coordinaciones estructurales, administrativas y parlamentarias
    P(
        body="national_coordinations",
        code="archive_coordination",
        name="Coordinación de Archivo del Partido",
        elect=PRES,
        basis="Art. 33 fracc. VI",
    ),
    P(
        body="national_coordinations",
        code="senate_group_coordination",
        name="Coordinación del Grupo Parlamentario en el Senado de la República",
        elect=CDIR,
        basis="Art. 32 fracc. VIII y 45 fracc. IV",
    ),
    P(
        body="national_coordinations",
        code="deputies_group_coordination",
        name="Coordinación del Grupo Parlamentario en la Cámara de Diputados",
        elect=CDIR,
        basis="Art. 32 fracc. VIII y 45 fracc. IV",
    ),
    P(
        body="national_coordinations",
        code="local_deputies_coordination",
        name="Coordinación Nacional de Diputaciones Locales",
        elect=CDIR,
        basis="Art. 19 fracc. VI, 32 fracc. VIII y 45 fracc. V",
    ),
    P(
        body="national_coordinations",
        code="municipalities_coordination",
        name="Coordinación Nacional de Ayuntamientos y Concejos de la Ciudad de México",
        elect=CDIR,
        basis="Art. 19 fracc. VII, 32 fracc. VIII y 45 fracc. VI",
    ),
    # 1.2 B. Coordinaciones especiales de la Presidencia del Consejo Directivo
    *[
        P(body="special_coordinations", code=code, name=name, elect=PRES, basis="Art. 33 fracc. XX")
        for code, name in [
            ("electoral_alliances_coordination", "Coordinación de Alianzas Electorales"),
            ("financing_coordination", "Coordinación de Financiamiento"),
            ("political_relations_coordination", "Coordinación de Relaciones Políticas"),
            ("parties_liaison_coordination", "Coordinación de Enlace con Partidos"),
            (
                "associations_liaison_coordination",
                "Coordinación de Enlace con Agrupaciones Políticas",
            ),
            ("state_delegates_coordination", "Coordinación de Personas Delegadas Estatales"),
        ]
    ],
    # 1.2 C. Coordinaciones nacionales de causas y movimientos sociales (Art. 94)
    *[
        P(
            body="causes_coordinations",
            code=f"cause_{number:02d}",
            name=name,
            elect="Comité Directivo Nacional (nombramiento expedido por la Presidencia del Consejo "
            "Directivo)",
            years=3,
            max_terms=2,
            basis=basis,
        )
        for number, (name, basis) in enumerate(
            [
                (
                    "Coordinación Nacional de Derechos Medioambientales, Agroalimentarios y "
                    "Comunitarios",
                    "Art. 94 fracc. I y 95",
                ),
                ("Coordinación Nacional Indígena", "Art. 94 fracc. II y 96"),
                ("Coordinación Nacional Obrera", "Art. 94 fracc. III y 97"),
                ("Coordinación Nacional Empresarial", "Art. 94 fracc. IV y 98"),
                ("Coordinación Nacional de Personas Migrantes", "Art. 94 fracc. V y 99"),
                ("Coordinación Nacional de Personas con Discapacidad", "Art. 94 fracc. VI y 100"),
                ("Coordinación Nacional de Adultos Mayores", "Art. 94 fracc. VII y 101"),
                (
                    "Coordinación Nacional de Juventudes Generación PAX / Coordinación Nacional de "
                    "Jóvenes",
                    "Art. 94 fracc. VIII y 102",
                ),
                (
                    "Coordinación Nacional de Atención a Organizaciones Sociales y Ciudadanas",
                    "Art. 94 fracc. IX",
                ),
                ("Coordinación Nacional para el Comercio Popular", "Art. 94 fracc. X"),
                (
                    "Coordinación Nacional de Promoción de la Salud y el Deporte",
                    "Art. 94 fracc. XI",
                ),
                ("Coordinación Nacional de Combate a las Adicciones", "Art. 94 fracc. XII"),
                ("Coordinación Nacional de Desarrollo Sustentable", "Art. 94 fracc. XIII"),
                (
                    "Coordinación Nacional para la Planeación del Desarrollo Industrial y Comercial",
                    "Art. 94 fracc. XIV",
                ),
                ("Coordinación Nacional de Fortalecimiento Municipal", "Art. 94 fracc. XV"),
                (
                    "Coordinación Nacional de Acceso a la Cultura y Derechos del Patrimonio Histórico",
                    "Art. 94 fracc. XVI",
                ),
                ("Coordinación Nacional de Personas Desaparecidas", "Art. 94 fracc. XVII"),
                (
                    "Coordinación Nacional de Combate al Delito y Seguridad Ciudadana",
                    "Art. 94 fracc. XVIII",
                ),
                (
                    "Coordinación Nacional de Cuidado y Protección de Animales de Compañía y Seres "
                    "Sintientes",
                    "Art. 94 fracc. XIX",
                ),
                ("Coordinación de la Red Nacional de Mujeres Lila", "Art. 94 fracc. XX y 103"),
                (
                    "Coordinación del Movimiento Nacional por la Vida y la Familia",
                    "Art. 94 fracc. XXI y 105",
                ),
                (
                    "Coordinación del Movimiento por la Paz y la Reconciliación Nacional",
                    "Art. 94 fracc. XXII y 106",
                ),
            ],
            start=1,
        )
    ],
    # 2.1 A. Consejo Directivo Estatal
    P(
        body="state_board",
        code="ced_president",
        name="Presidencia del Consejo Directivo Estatal",
        elect=CN,
        years=3,
    ),
    P(
        body="state_board",
        code="ced_sg_political_relations",
        name="Secretaría General de Relaciones Políticas Estatal",
        elect=CN,
        years=3,
    ),
    P(
        body="state_board",
        code="ced_sg_electoral_strategy",
        name="Secretaría General de Estrategia Electoral Estatal",
        elect=CN,
        years=3,
    ),
    # Direcciones y Tesorería del Comité Directivo Estatal
    P(
        body="state_committee",
        code="cde_administration_finance",
        name="Dirección de Administración y Finanzas Estatal",
        elect=CE,
        years=3,
    ),
    P(
        body="state_committee",
        code="cde_treasury",
        name="Tesorería del Comité Directivo Estatal",
        elect="Propuesta por la Dirección de Administración y Finanzas del Comité Directivo Estatal y "
        "aprobada por la Secretaría de Administración y Finanzas Nacional",
        years=3,
        basis="Art. 37 fracc. XXVII",
    ),
    P(
        body="state_committee",
        code="cde_legal",
        name="Dirección Jurídica Estatal",
        elect=CE,
        years=3,
    ),
    P(
        body="state_committee",
        code="cde_strategy_communication",
        name="Dirección de Estrategia y Comunicación Política Estatal",
        elect=CE,
        years=3,
    ),
    P(
        body="state_committee",
        code="cde_causes",
        name="Dirección de Causas y Movimientos Sociales Estatal",
        elect=CE,
        years=3,
    ),
    P(
        body="state_committee",
        code="cde_peace_foundation",
        name="Dirección de la Fundación de Investigación y Promoción de la Cultura de la Paz Estatal",
        elect=CE,
        years=3,
    ),
    P(
        body="state_committee",
        code="state_transparency_coordination",
        name="Coordinación de la Unidad de Transparencia Estatal",
        elect=CE,
        years=3,
        basis="Art. 81 fracc. VII",
    ),
    # 2.1 B. Comisión Política Estatal
    P(
        body="state_political_commission",
        code="cpe_president",
        name="Presidencia de la Comisión Política Estatal",
        elect=CE,
        years=3,
    ),
    P(
        body="state_political_commission",
        code="cpe_technical_secretary",
        name="Secretaría Técnica de la Comisión Política Estatal",
        elect=CE,
        years=3,
    ),
    P(
        body="state_political_commission",
        code="state_federal_deputies_coordination",
        name="Coordinación de las Diputaciones Federales en la Entidad",
        basis="Art. 77 fracc. VI",
    ),
    # 2.1 C. Presídium del Congreso Estatal (derived)
    P(
        body="state_presidium",
        code="sp_president",
        name="Presidencia del Presídium Estatal",
        derived=["ced_president"],
    ),
    P(
        body="state_presidium",
        code="sp_vice_president",
        name="Vicepresidencia del Presídium Estatal",
        derived=["ced_sg_electoral_strategy"],
    ),
    P(
        body="state_presidium",
        code="sp_secretary",
        name="Secretaría del Presídium Estatal",
        derived=["cpe_president"],
    ),
    # 2.2 Coordinaciones estatales
    P(
        body="state_coordinations",
        code="state_local_group_coordination",
        name="Coordinación del Grupo Parlamentario en el Congreso Local",
        elect="Consejo Directivo Nacional en coordinación con la Presidencia del Comité Directivo "
        "Estatal",
        basis="Art. 32 fracc. VIII y 69 fracc. V",
    ),
    P(
        body="state_coordinations",
        code="state_municipalities_coordination",
        name="Coordinación Estatal de Ayuntamientos y Concejos de la Ciudad de México",
        basis="Art. 69 fracc. VI",
    ),
    # 3.1 Comité Directivo Distrital
    *[
        P(body="district_committee", code=f"cdd_{code}", name=name, elect=CE, years=3)
        for code, name in [
            ("president", "Presidencia del Comité Directivo Distrital"),
            ("secretary_general", "Secretaría General del Comité Directivo Distrital"),
            (
                "electoral_strategy",
                "Secretaría de Estrategia Electoral del Comité Directivo Distrital",
            ),
            (
                "administration_finance",
                "Dirección de Administración y Finanzas del Comité Directivo Distrital",
            ),
            ("legal", "Dirección Jurídica del Comité Directivo Distrital"),
        ]
    ],
    # 4.1 Comité Directivo Municipal o de Alcaldía
    *[
        P(body="municipal_committee", code=f"cdm_{code}", name=name, elect=CE, years=3)
        for code, name in [
            ("president", "Presidencia del Comité Directivo Municipal o de Alcaldía"),
            (
                "secretary_general",
                "Secretaría General del Comité Directivo Municipal o de Alcaldía",
            ),
            (
                "electoral_strategy",
                "Secretaría de Estrategia Electoral del Comité Directivo Municipal o de Alcaldía",
            ),
            (
                "administration_finance",
                "Dirección de Administración y Finanzas del Comité Directivo Municipal o de Alcaldía",
            ),
            ("legal", "Dirección Jurídica del Comité Directivo Municipal o de Alcaldía"),
        ]
    ],
]

COORDINATION_POSITIONS = [
    ("federal", "coordinator", "Coordinación federal"),
    ("local", "coordinator", "Coordinación local"),
    ("sectional", "coordinator", "Coordinación seccional"),
]

PERMISSIONS = [
    (
        "party_structure.catalog.manage",
        "catalog_manage",
        "Órganos, cargos, incompatibilidades, cargos de coordinación y roles por defecto",
    ),
    ("party_structure.body.read", "body_read", "Consultar órganos y asientos"),
    ("party_structure.body.write", "body_write", "Registrar instalación y disolución de comités"),
]
# D-105: base roles of the structure, with TOTP. System roles (D-107): the catalog points to
# them, so they cannot be deleted; their permissions stay editable from the panel.
ROLES = [
    (
        LEADER,
        "Dirigente territorial",
        "Cargos de órganos estatutarios: gestiona la estructura de su territorio.",
        ["party_structure.body.read", "party_structure.body.write"],
    ),
    (
        "territorial_coordinator",
        "Coordinador territorial",
        "Cargos de coordinaciones territoriales: consulta su estructura.",
        ["party_structure.body.read"],
    ),
]
GRANTS = {
    "admin": [code for code, *_ in PERMISSIONS],
    "coordinator": ["party_structure.body.read", "party_structure.body.write"],
    "viewer": ["party_structure.body.read"],
}


def _seed() -> None:
    bind = op.get_bind()
    for code, action, description in PERMISSIONS:
        bind.execute(
            sa.text(
                "INSERT INTO identity.permissions (code, module, action, description) "
                "VALUES (:code, 'party_structure', :action, :description)"
            ),
            {"code": code, "action": action, "description": description},
        )
    for code, name, description, codes in ROLES:
        bind.execute(
            sa.text(
                "INSERT INTO identity.roles (code, name, description, requires_mfa, is_system, "
                "grants_all) VALUES (:code, :name, :description, true, true, false)"
            ),
            {"code": code, "name": name, "description": description},
        )
        GRANTS.setdefault(code, []).extend(codes)
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
    for order, (code, name, level, installation, basis) in enumerate(BODY_TYPES, start=1):
        bind.execute(
            sa.text(
                "INSERT INTO party_structure.body_types (code, name, territorial_level, "
                "requires_installation, statutory_basis, sort_order) "
                "VALUES (:code, :name, :level, :installation, :basis, :order)"
            ),
            {
                "code": code,
                "name": name,
                "level": level,
                "installation": installation,
                "basis": basis,
                "order": order,
            },
        )
    basis_of = {code: basis for code, _, _, _, basis in BODY_TYPES}
    for order, item in enumerate(POSITIONS, start=1):
        bind.execute(
            sa.text(
                "INSERT INTO party_structure.position_types (body_type_id, code, name, "
                "scope_rule, electing_body, term_years, term_months, max_consecutive_terms, "
                "statutory_basis, default_role_id, is_derived, sort_order) "
                "SELECT b.id, :code, :name, :scope, :elect, :years, NULL, :max_terms, :basis, "
                "CASE WHEN :derived THEN NULL ELSE "
                "(SELECT id FROM identity.roles WHERE code = :role) END, :derived, :order "
                "FROM party_structure.body_types b WHERE b.code = :body"
            ),
            {
                "body": item["body"],
                "code": item["code"],
                "name": item["name"],
                "scope": item.get("scope", "body_territory"),
                "elect": item.get("elect"),
                "years": item.get("years"),
                "max_terms": item.get("max_terms"),
                "basis": item.get("basis", basis_of[item["body"]]),
                "role": LEADER,
                "derived": bool(item.get("derived")),
                "order": order,
            },
        )
    for item in POSITIONS:
        for source in item.get("derived", []):
            bind.execute(
                sa.text(
                    "INSERT INTO party_structure.position_derivations "
                    "(position_type_id, source_position_type_id) "
                    "SELECT d.id, s.id FROM party_structure.position_types d, "
                    "party_structure.position_types s WHERE d.code = :derived AND s.code = :source"
                ),
                {"derived": item["code"], "source": source},
            )
    for order, (kind, code, name) in enumerate(COORDINATION_POSITIONS, start=1):
        bind.execute(
            sa.text(
                "INSERT INTO party_structure.coordination_position_types "
                "(kind, code, name, default_role_id, sort_order) VALUES (:kind, :code, :name, "
                "(SELECT id FROM identity.roles WHERE code = 'territorial_coordinator'), :order)"
            ),
            {"kind": kind, "code": code, "name": name, "order": order},
        )
    # National bodies (one each) and the bodies of the 32 states (INE codes 1-32), installed.
    bind.execute(
        sa.text(
            "INSERT INTO party_structure.bodies (body_type_id) SELECT id "
            "FROM party_structure.body_types WHERE territorial_level = 'national'"
        )
    )
    bind.execute(
        sa.text(
            "INSERT INTO party_structure.bodies (body_type_id, state_code) "
            "SELECT b.id, s.code FROM party_structure.body_types b, generate_series(1, 32) s(code) "
            "WHERE b.territorial_level = 'state'"
        )
    )


def _unseed() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM identity.permissions WHERE code = ANY(:codes)"),
        {"codes": [code for code, *_ in PERMISSIONS]},
    )
    bind.execute(
        sa.text("DELETE FROM identity.roles WHERE code = ANY(:codes)"),
        {"codes": [code for code, *_ in ROLES]},
    )


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS party_structure")
    op.execute("REVOKE ALL ON SCHEMA party_structure FROM PUBLIC")
    role = app_role()
    op.execute(
        if_role_exists(
            role,
            f"""
            GRANT USAGE ON SCHEMA party_structure TO {role};
            ALTER DEFAULT PRIVILEGES IN SCHEMA party_structure
              GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role};
            """,
        )
    )
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "body_types",
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
        sa.Column("code", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column("territorial_level", sa.Text(), nullable=False),
        sa.Column("requires_installation", sa.Boolean(), nullable=False),
        sa.Column("statutory_basis", sqlmodel.sql.sqltypes.AutoString(length=300), nullable=True),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "territorial_level IN ('national', 'state', 'district', 'municipal')",
            name=op.f("ck_body_types_territorial_level"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_body_types")),
        schema="party_structure",
    )
    op.create_index(
        "uq_body_types_code",
        "body_types",
        ["code"],
        unique=True,
        schema="party_structure",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "coordination_position_types",
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
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("code", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column("default_role_id", sa.Uuid(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('federal', 'local', 'sectional')",
            name=op.f("ck_coordination_position_types_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["default_role_id"],
            ["identity.roles.id"],
            name=op.f("fk_coordination_position_types_default_role_id__roles"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coordination_position_types")),
        schema="party_structure",
    )
    op.create_index(
        op.f("ix_coordination_position_types_default_role_id"),
        "coordination_position_types",
        ["default_role_id"],
        unique=False,
        schema="party_structure",
    )
    op.create_index(
        "uq_coordination_position_types_kind_code",
        "coordination_position_types",
        ["kind", "code"],
        unique=True,
        schema="party_structure",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "position_types",
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
        sa.Column("body_type_id", sa.Uuid(), nullable=False),
        sa.Column("code", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column("scope_rule", sa.Text(), nullable=False),
        sa.Column("electing_body", sqlmodel.sql.sqltypes.AutoString(length=300), nullable=True),
        sa.Column("term_years", sa.SmallInteger(), nullable=True),
        sa.Column("term_months", sa.SmallInteger(), nullable=True),
        sa.Column("max_consecutive_terms", sa.SmallInteger(), nullable=True),
        sa.Column("statutory_basis", sqlmodel.sql.sqltypes.AutoString(length=300), nullable=True),
        sa.Column("default_role_id", sa.Uuid(), nullable=True),
        sa.Column("is_derived", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "scope_rule IN ('body_territory', 'circumscription', 'national')",
            name=op.f("ck_position_types_scope_rule"),
        ),
        sa.CheckConstraint(
            "max_consecutive_terms IS NULL OR max_consecutive_terms > 0",
            name=op.f("ck_position_types_max_consecutive_terms"),
        ),
        sa.CheckConstraint(
            "term_months IS NULL OR term_months > 0", name=op.f("ck_position_types_term_months")
        ),
        sa.CheckConstraint(
            "term_years IS NULL OR term_years > 0", name=op.f("ck_position_types_term_years")
        ),
        sa.ForeignKeyConstraint(
            ["body_type_id"],
            ["party_structure.body_types.id"],
            name=op.f("fk_position_types_body_type_id__body_types"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["default_role_id"],
            ["identity.roles.id"],
            name=op.f("fk_position_types_default_role_id__roles"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_position_types")),
        schema="party_structure",
    )
    op.create_index(
        op.f("ix_position_types_body_type_id"),
        "position_types",
        ["body_type_id"],
        unique=False,
        schema="party_structure",
    )
    op.create_index(
        op.f("ix_position_types_default_role_id"),
        "position_types",
        ["default_role_id"],
        unique=False,
        schema="party_structure",
    )
    op.create_index(
        "uq_position_types_code",
        "position_types",
        ["code"],
        unique=True,
        schema="party_structure",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "position_derivations",
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
        sa.Column("position_type_id", sa.Uuid(), nullable=False),
        sa.Column("source_position_type_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["position_type_id"],
            ["party_structure.position_types.id"],
            name=op.f("fk_position_derivations_position_type_id__position_types"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_position_type_id"],
            ["party_structure.position_types.id"],
            name=op.f("fk_position_derivations_source_position_type_id__position_types"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_position_derivations")),
        schema="party_structure",
    )
    op.create_index(
        op.f("ix_position_derivations_position_type_id"),
        "position_derivations",
        ["position_type_id"],
        unique=False,
        schema="party_structure",
    )
    op.create_index(
        op.f("ix_position_derivations_source_position_type_id"),
        "position_derivations",
        ["source_position_type_id"],
        unique=False,
        schema="party_structure",
    )
    op.create_index(
        "uq_position_derivations_pair",
        "position_derivations",
        ["position_type_id", "source_position_type_id"],
        unique=True,
        schema="party_structure",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "position_incompatibilities",
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
        sa.Column("position_type_a_id", sa.Uuid(), nullable=False),
        sa.Column("position_type_b_id", sa.Uuid(), nullable=False),
        sa.Column("notes", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.CheckConstraint(
            "position_type_a_id < position_type_b_id",
            name=op.f("ck_position_incompatibilities_ordered_pair"),
        ),
        sa.ForeignKeyConstraint(
            ["position_type_a_id"],
            ["party_structure.position_types.id"],
            name=op.f("fk_position_incompatibilities_position_type_a_id__position_types"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["position_type_b_id"],
            ["party_structure.position_types.id"],
            name=op.f("fk_position_incompatibilities_position_type_b_id__position_types"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_position_incompatibilities")),
        schema="party_structure",
    )
    op.create_index(
        op.f("ix_position_incompatibilities_position_type_a_id"),
        "position_incompatibilities",
        ["position_type_a_id"],
        unique=False,
        schema="party_structure",
    )
    op.create_index(
        op.f("ix_position_incompatibilities_position_type_b_id"),
        "position_incompatibilities",
        ["position_type_b_id"],
        unique=False,
        schema="party_structure",
    )
    op.create_index(
        "uq_position_incompatibilities_pair",
        "position_incompatibilities",
        ["position_type_a_id", "position_type_b_id"],
        unique=True,
        schema="party_structure",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "bodies",
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
        sa.Column("body_type_id", sa.Uuid(), nullable=False),
        sa.Column("state_code", sa.SmallInteger(), nullable=True),
        sa.Column("framework_id", sa.Uuid(), nullable=True),
        sa.Column("municipality_id", sa.Uuid(), nullable=True),
        sa.Column("federal_district_id", sa.Uuid(), nullable=True),
        sa.Column("local_district_id", sa.Uuid(), nullable=True),
        sa.Column("district_kind", sa.Text(), nullable=True),
        sa.Column("installed_on", sa.Date(), nullable=True),
        sa.Column(
            "installation_agreement", sqlmodel.sql.sqltypes.AutoString(length=300), nullable=True
        ),
        sa.Column("dissolved_on", sa.Date(), nullable=True),
        sa.Column(
            "dissolution_agreement", sqlmodel.sql.sqltypes.AutoString(length=300), nullable=True
        ),
        sa.CheckConstraint(
            "district_kind IN ('federal', 'local')", name=op.f("ck_bodies_district_kind")
        ),
        sa.CheckConstraint(
            "(municipality_id IS NULL AND federal_district_id IS NULL AND local_district_id IS NULL) = (framework_id IS NULL)",
            name=op.f("ck_bodies_node_has_framework"),
        ),
        sa.CheckConstraint(
            "dissolved_on IS NULL OR installed_on IS NULL OR dissolved_on >= installed_on",
            name=op.f("ck_bodies_dates"),
        ),
        sa.CheckConstraint(
            "num_nonnulls(municipality_id, federal_district_id, local_district_id) <= 1",
            name=op.f("ck_bodies_one_node"),
        ),
        sa.CheckConstraint(
            "state_code IS NULL OR state_code BETWEEN 1 AND 32", name=op.f("ck_bodies_state_code")
        ),
        sa.ForeignKeyConstraint(
            ["body_type_id"],
            ["party_structure.body_types.id"],
            name=op.f("fk_bodies_body_type_id__body_types"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["federal_district_id"],
            ["geography.federal_districts.id"],
            name=op.f("fk_bodies_federal_district_id__federal_districts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["framework_id"],
            ["geography.geographic_frameworks.id"],
            name=op.f("fk_bodies_framework_id__geographic_frameworks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["local_district_id"],
            ["geography.local_districts.id"],
            name=op.f("fk_bodies_local_district_id__local_districts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["municipality_id"],
            ["geography.municipalities.id"],
            name=op.f("fk_bodies_municipality_id__municipalities"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bodies")),
        schema="party_structure",
    )
    op.create_index(
        op.f("ix_bodies_body_type_id"),
        "bodies",
        ["body_type_id"],
        unique=False,
        schema="party_structure",
    )
    op.create_index(
        op.f("ix_bodies_federal_district_id"),
        "bodies",
        ["federal_district_id"],
        unique=False,
        schema="party_structure",
    )
    op.create_index(
        op.f("ix_bodies_framework_id"),
        "bodies",
        ["framework_id"],
        unique=False,
        schema="party_structure",
    )
    op.create_index(
        op.f("ix_bodies_local_district_id"),
        "bodies",
        ["local_district_id"],
        unique=False,
        schema="party_structure",
    )
    op.create_index(
        op.f("ix_bodies_municipality_id"),
        "bodies",
        ["municipality_id"],
        unique=False,
        schema="party_structure",
    )
    op.create_index(
        op.f("ix_bodies_state_code"),
        "bodies",
        ["state_code"],
        unique=False,
        schema="party_structure",
    )
    op.create_index(
        "uq_bodies_current",
        "bodies",
        [
            "body_type_id",
            sa.literal_column("coalesce(state_code, 0)"),
            sa.literal_column(
                "coalesce(municipality_id, federal_district_id, local_district_id, '00000000-0000-0000-0000-000000000000'::uuid)"
            ),
        ],
        unique=True,
        schema="party_structure",
        postgresql_where=sa.text("dissolved_on IS NULL AND deleted_at IS NULL"),
    )
    # ### end Alembic commands ###
    _seed()


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(
        "uq_bodies_current",
        table_name="bodies",
        schema="party_structure",
        postgresql_where=sa.text("dissolved_on IS NULL AND deleted_at IS NULL"),
    )
    op.drop_index(op.f("ix_bodies_state_code"), table_name="bodies", schema="party_structure")
    op.drop_index(op.f("ix_bodies_municipality_id"), table_name="bodies", schema="party_structure")
    op.drop_index(
        op.f("ix_bodies_local_district_id"), table_name="bodies", schema="party_structure"
    )
    op.drop_index(op.f("ix_bodies_framework_id"), table_name="bodies", schema="party_structure")
    op.drop_index(
        op.f("ix_bodies_federal_district_id"), table_name="bodies", schema="party_structure"
    )
    op.drop_index(op.f("ix_bodies_body_type_id"), table_name="bodies", schema="party_structure")
    op.drop_table("bodies", schema="party_structure")
    op.drop_index(
        "uq_position_incompatibilities_pair",
        table_name="position_incompatibilities",
        schema="party_structure",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(
        op.f("ix_position_incompatibilities_position_type_b_id"),
        table_name="position_incompatibilities",
        schema="party_structure",
    )
    op.drop_index(
        op.f("ix_position_incompatibilities_position_type_a_id"),
        table_name="position_incompatibilities",
        schema="party_structure",
    )
    op.drop_table("position_incompatibilities", schema="party_structure")
    op.drop_index(
        "uq_position_derivations_pair",
        table_name="position_derivations",
        schema="party_structure",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(
        op.f("ix_position_derivations_source_position_type_id"),
        table_name="position_derivations",
        schema="party_structure",
    )
    op.drop_index(
        op.f("ix_position_derivations_position_type_id"),
        table_name="position_derivations",
        schema="party_structure",
    )
    op.drop_table("position_derivations", schema="party_structure")
    op.drop_index(
        "uq_position_types_code",
        table_name="position_types",
        schema="party_structure",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(
        op.f("ix_position_types_default_role_id"),
        table_name="position_types",
        schema="party_structure",
    )
    op.drop_index(
        op.f("ix_position_types_body_type_id"),
        table_name="position_types",
        schema="party_structure",
    )
    op.drop_table("position_types", schema="party_structure")
    op.drop_index(
        "uq_coordination_position_types_kind_code",
        table_name="coordination_position_types",
        schema="party_structure",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(
        op.f("ix_coordination_position_types_default_role_id"),
        table_name="coordination_position_types",
        schema="party_structure",
    )
    op.drop_table("coordination_position_types", schema="party_structure")
    op.drop_index(
        "uq_body_types_code",
        table_name="body_types",
        schema="party_structure",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("body_types", schema="party_structure")
    # ### end Alembic commands ###
    _unseed()
    op.execute("DROP SCHEMA IF EXISTS party_structure")
