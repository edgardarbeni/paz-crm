"""CURP rules (D-30) checked against python-stdnum's independent implementation."""

import random
from datetime import date

import pytest
from stdnum.mx import curp as stdnum_curp

from app.modules.people import curp


def build(prefix: str) -> str:
    return prefix + curp.check_digit(prefix)


VALID = build("GOME050101MASRRNA")


def test_documented_vector() -> None:
    data = curp.parse("BOXW310820HNERXN09")
    assert data.birth_date == date(1931, 8, 20)
    assert data.sex == "H"
    assert data.birth_entity == "NE"


def test_check_digit_matches_stdnum_on_random_curps() -> None:
    rng = random.Random(20261024)  # noqa: S311 - deterministic test data
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    consonants = "BCDFGHJKLMNPQRSTVWXYZ"
    for _ in range(300):
        prefix = (
            rng.choice(letters)
            + rng.choice("AEIOUX")
            + rng.choice(letters)
            + rng.choice(letters)
            + f"{rng.randint(0, 99):02d}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}"
            + rng.choice("HM")
            + rng.choice([code for code in curp.ENTITIES if code != "NE"])
            + "".join(rng.choice(consonants) for _ in range(3))
            + rng.choice("0123456789ABC")
        )
        value = build(prefix)
        assert stdnum_curp.calc_check_digit(prefix) == value[17]
        assert curp.parse(value).curp == stdnum_curp.validate(value)


def test_century_and_normalization() -> None:
    value = build("GOME050101MASRRNA")
    data = curp.parse(f"  {value.lower()} ")
    assert data.birth_date == date(2005, 1, 1)
    assert data.sex == "M"
    assert data.birth_entity == "AS"


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("XXXX", "estructura"),
        ("GOME050101MZZRRNA1", "estructura"),  # unknown entity
        (VALID[:17] + str((int(VALID[17]) + 1) % 10), "verificador"),
        (build("GOME050230MASRRNA"), "no existe"),  # 30 Feb
    ],
)
def test_invalid(value: str, message: str) -> None:
    with pytest.raises(curp.CurpError, match=message):
        curp.parse(value)


def test_coherence_and_mask() -> None:
    data = curp.parse(build("GOME050101MASRRNA"))
    assert curp.coherence(data, birth_date=date(2005, 1, 1), sex="M", birth_entity="AS") == []
    problems = curp.coherence(data, birth_date=date(2005, 1, 2), sex="H", birth_entity="JC")
    assert len(problems) == 3
    assert curp.mask(data.curp) == "GOME******" + data.curp[10:]
    assert curp.mask("corta") == "******"
