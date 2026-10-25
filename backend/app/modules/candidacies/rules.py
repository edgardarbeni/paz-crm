"""Business-rule engine (D-28). Rules are data: enabled, severity and parameters per process
(and optionally per office). Only "unique_person_in_process" is enabled by default; electoral
rules (parity, alternation, substitute sex) are switched on per state and process according
to the applicable law — the system never assumes them.

Each rule returns violations; blocking ones stop the operation unless a user with
`candidacies.rule.override` accepts them with a reason (stored in `rule_overrides`).
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.candidacies.models import Severity


@dataclass(frozen=True, slots=True)
class Violation:
    rule: str
    severity: Severity
    message: str
    formula_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class RuleConfig:
    rule_id: uuid.UUID
    code: str
    severity: Severity
    params: dict[str, Any]


@dataclass
class Evaluation:
    violations: list[Violation] = field(default_factory=list)

    @property
    def blocking(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == Severity.BLOCKING]

    @property
    def warnings(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == Severity.WARNING]


async def active_rules(
    db: AsyncSession, process_id: uuid.UUID, office_type_id: uuid.UUID
) -> dict[str, RuleConfig]:
    """Process-wide rules overridden by office-specific ones."""
    rows = (
        await db.execute(
            text(
                "SELECT vr.id, vr.code, pvr.severity, vr.default_params || pvr.params AS params, "
                "pvr.is_enabled, pvr.office_type_id FROM candidacies.process_validation_rules pvr "
                "JOIN candidacies.validation_rules vr ON vr.id = pvr.validation_rule_id "
                "WHERE pvr.process_id = :p AND pvr.deleted_at IS NULL "
                "AND (pvr.office_type_id IS NULL OR pvr.office_type_id = :o) "
                "ORDER BY pvr.office_type_id NULLS FIRST"
            ),
            {"p": process_id, "o": office_type_id},
        )
    ).mappings()
    configs: dict[str, RuleConfig] = {}
    for row in rows:
        if row["is_enabled"]:
            configs[row["code"]] = RuleConfig(
                row["id"], row["code"], Severity(row["severity"]), dict(row["params"])
            )
        else:
            configs.pop(row["code"], None)  # office-specific disable wins
    return configs


# --- context -------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FormulaFacts:
    id: uuid.UUID
    office_type_id: uuid.UUID
    position: int
    owner_id: uuid.UUID | None
    owner_sex: str | None
    substitute_id: uuid.UUID | None
    substitute_sex: str | None


async def nomination_facts(db: AsyncSession, nomination_id: uuid.UUID) -> list[FormulaFacts]:
    rows = (
        await db.execute(
            text(
                "SELECT f.id, f.office_type_id, f.position, "
                "o.person_id AS owner_id, po.sex AS owner_sex, s.person_id AS substitute_id, "
                "ps.sex AS substitute_sex "
                "FROM candidacies.formulas f "
                "LEFT JOIN candidacies.formula_members o ON o.formula_id = f.id AND o.member_role "
                "= 'owner' AND o.deleted_at IS NULL "
                "LEFT JOIN people.persons po ON po.id = o.person_id "
                "LEFT JOIN candidacies.formula_members s ON s.formula_id = f.id AND s.member_role "
                "= 'substitute' AND s.deleted_at IS NULL "
                "LEFT JOIN people.persons ps ON ps.id = s.person_id "
                "WHERE f.nomination_id = :n AND f.deleted_at IS NULL "
                "AND f.status IN ('aspirant', 'registered', 'approved') "
                "ORDER BY f.office_type_id, f.position"
            ),
            {"n": nomination_id},
        )
    ).mappings()
    return [FormulaFacts(**row) for row in rows]


# --- rules ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Context:
    db: AsyncSession
    process_id: uuid.UUID
    nomination_id: uuid.UUID
    facts: list[FormulaFacts]
    final: bool  # submitting/approving: nomination-wide rules (parity) apply


RuleFn = Callable[[Context, RuleConfig], Awaitable[list[Violation]]]


def _violation(config: RuleConfig, message: str, formula_id: uuid.UUID | None = None) -> Violation:
    return Violation(config.code, config.severity, message, formula_id)


async def unique_person_in_process(ctx: Context, config: RuleConfig) -> list[Violation]:
    violations = []
    for fact in ctx.facts:
        for person_id, role in ((fact.owner_id, "propietaria"), (fact.substitute_id, "suplente")):
            if person_id is None:
                continue
            others = (
                await ctx.db.execute(
                    text(
                        "SELECT count(*) FROM candidacies.formula_members fm "
                        "JOIN candidacies.formulas f ON f.id = fm.formula_id "
                        "WHERE fm.process_id = :p AND fm.person_id = :person "
                        "AND fm.deleted_at IS NULL AND f.deleted_at IS NULL "
                        "AND f.status IN ('aspirant', 'registered', 'approved') AND f.id <> "
                        ":formula"
                    ),
                    {"p": ctx.process_id, "person": person_id, "formula": fact.id},
                )
            ).scalar_one()
            if others:
                message = (
                    f"La persona {role} de la posición {fact.position} "
                    "ya integra otra fórmula del proceso."
                )
                violations.append(_violation(config, message, fact.id))
    return violations


async def substitute_same_sex(ctx: Context, config: RuleConfig) -> list[Violation]:
    allow_mixed = bool(config.params.get("allow_male_owner_female_substitute", False))
    violations = []
    for fact in ctx.facts:
        if fact.owner_id is None or fact.substitute_id is None:
            continue
        if fact.owner_sex is None or fact.substitute_sex is None:
            message = f"Posición {fact.position}: falta registrar el sexo para validar la fórmula."
            violations.append(_violation(config, message, fact.id))
        elif fact.owner_sex != fact.substitute_sex and not (
            allow_mixed and fact.owner_sex == "H" and fact.substitute_sex == "M"
        ):
            message = (
                f"Posición {fact.position}: la persona suplente no es del mismo sexo "
                "que la propietaria."
            )
            violations.append(_violation(config, message, fact.id))
    return violations


async def list_alternation(ctx: Context, config: RuleConfig) -> list[Violation]:
    violations = []
    by_office: dict[uuid.UUID, list[FormulaFacts]] = {}
    for fact in ctx.facts:
        by_office.setdefault(fact.office_type_id, []).append(fact)
    for office_facts in by_office.values():
        for previous, current in pairwise(sorted(office_facts, key=lambda f: f.position)):
            consecutive = current.position == previous.position + 1
            if consecutive and previous.owner_sex and previous.owner_sex == current.owner_sex:
                message = (
                    f"Posiciones {previous.position} y {current.position}: no alternan el sexo."
                )
                violations.append(_violation(config, message, current.id))
    return violations


async def gender_parity(ctx: Context, config: RuleConfig) -> list[Violation]:
    """Evaluated when submitting/approving: heads (position 1 of the head office) of the
    submitted/approved nominations of the same office in the process, plus this one."""
    if not ctx.final:
        return []
    minimum = float(config.params.get("min_female_ratio", 0.5))
    row = (
        (
            await ctx.db.execute(
                text(
                    "SELECT count(*) AS total, count(*) FILTER (WHERE p.sex = 'M') AS women "
                    "FROM candidacies.nominations n "
                    "JOIN candidacies.formulas f ON f.nomination_id = n.id "
                    "  AND f.office_type_id = n.office_type_id AND f.position = 1 "
                    "  AND f.deleted_at IS NULL AND f.status IN ('aspirant', 'registered', "
                    "'approved') "
                    "JOIN candidacies.formula_members m ON m.formula_id = f.id "
                    "  AND m.member_role = 'owner' AND m.deleted_at IS NULL "
                    "JOIN people.persons p ON p.id = m.person_id "
                    "WHERE n.process_id = :p AND n.deleted_at IS NULL AND n.office_type_id = "
                    "  (SELECT office_type_id FROM candidacies.nominations WHERE id = :n) "
                    "AND (n.status IN ('submitted', 'approved') OR n.id = :n)"
                ),
                {"p": ctx.process_id, "n": ctx.nomination_id},
            )
        )
        .mappings()
        .one()
    )
    total, women = int(row["total"]), int(row["women"])
    if total and women / total < minimum:
        message = (
            f"Paridad: {women} de {total} postulaciones encabezadas por mujeres "
            f"({women / total:.0%}); el mínimo configurado es {minimum:.0%}."
        )
        return [_violation(config, message)]
    return []


RULES: dict[str, RuleFn] = {
    "unique_person_in_process": unique_person_in_process,
    "substitute_same_sex": substitute_same_sex,
    "list_alternation": list_alternation,
    "gender_parity": gender_parity,
}


async def evaluate(
    db: AsyncSession,
    *,
    process_id: uuid.UUID,
    nomination_id: uuid.UUID,
    office_type_id: uuid.UUID,
    final: bool = False,
) -> tuple[Evaluation, dict[str, RuleConfig]]:
    configs = await active_rules(db, process_id, office_type_id)
    ctx = Context(db, process_id, nomination_id, await nomination_facts(db, nomination_id), final)
    evaluation = Evaluation()
    for code, config in configs.items():
        rule = RULES.get(code)
        if rule is not None:
            evaluation.violations.extend(await rule(ctx, config))
    return evaluation, configs
