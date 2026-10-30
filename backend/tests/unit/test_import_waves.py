"""Ordering of an import so recruiters in the file are written before their recruits."""

from app.modules.peace_movement.intake import _normalize, _waves


def row(curp: str, recruiter: str = "") -> dict[str, str]:
    return {"curp": curp, "curp_reclutador": recruiter}


def test_waves_follow_recruitment_inside_the_file() -> None:
    rows = [row("C", "B"), row("A"), row("B", "A"), row("D", "EXTERNO"), row("E", "e")]
    waves, parent, cyclic = _waves(rows)
    assert waves == [[1, 3, 4], [2], [0]]
    assert parent == {0: 2, 2: 1}
    assert cyclic == set()


def test_cycles_are_reported_not_ordered() -> None:
    rows = [row("A", "B"), row("B", "A"), row("C", "A"), row("D")]
    waves, _, cyclic = _waves(rows)
    assert cyclic == {0, 1, 2}
    assert waves == [[3]]


def test_headers_are_normalized() -> None:
    assert _normalize("  Sección ") == "seccion"
    assert _normalize("CURP-Reclutador") == "curp_reclutador"
    assert _normalize("Apellido  paterno") == "apellido_paterno"
