"""CURP validation (D-30): official structure, check digit and coherence with captured data.

The check digit is RENAPO's modulo-10 over the first 17 characters with the alphabet
``0-9 A-N Ñ O-Z`` (verified against python-stdnum's documented vectors in the tests).
No RENAPO lookup is performed.
"""

import re
from dataclasses import dataclass
from datetime import date

_ALPHABET = "0123456789ABCDEFGHIJKLMNÑOPQRSTUVWXYZ"

# Entity codes used in position 12-13 (32 states + NE: born abroad).
ENTITIES: dict[str, int | None] = {
    "AS": 1, "BC": 2, "BS": 3, "CC": 4, "CL": 5, "CM": 6, "CS": 7, "CH": 8, "DF": 9, "DG": 10,
    "GT": 11, "GR": 12, "HG": 13, "JC": 14, "MC": 15, "MN": 16, "MS": 17, "NT": 18, "NL": 19,
    "OC": 20, "PL": 21, "QT": 22, "QR": 23, "SP": 24, "SL": 25, "SR": 26, "TC": 27, "TS": 28,
    "TL": 29, "VZ": 30, "YN": 31, "ZS": 32, "NE": None,
}  # fmt: skip

_PATTERN = re.compile(
    r"^[A-Z][AEIOUX][A-Z]{2}"  # surname/name initials
    r"\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])"  # yymmdd
    r"[HMX]"  # sex
    rf"({'|'.join(ENTITIES)})"  # birth entity
    r"[B-DF-HJ-NP-TV-Z]{3}"  # internal consonants
    r"[0-9A-Z]"  # century differentiator
    r"\d$"  # check digit
)


class CurpError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CurpData:
    curp: str
    birth_date: date
    sex: str  # H | M | X
    birth_entity: str  # two-letter code (NE = born abroad)


def normalize(value: str) -> str:
    return "".join(value.split()).upper()


def check_digit(first_17: str) -> str:
    total = sum(_ALPHABET.index(char) * (18 - index) for index, char in enumerate(first_17[:17]))
    return str((10 - total % 10) % 10)


def parse(value: str) -> CurpData:
    curp = normalize(value)
    if len(curp) != 18 or not _PATTERN.match(curp):
        raise CurpError("La CURP no tiene una estructura válida.")
    if check_digit(curp) != curp[17]:
        raise CurpError("El dígito verificador de la CURP no corresponde.")
    century = 1900 if curp[16].isdigit() else 2000
    try:
        birth = date(century + int(curp[4:6]), int(curp[6:8]), int(curp[8:10]))
    except ValueError:
        raise CurpError("La fecha de nacimiento de la CURP no existe.") from None
    return CurpData(curp=curp, birth_date=birth, sex=curp[10], birth_entity=curp[11:13])


def coherence(
    data: CurpData, *, birth_date: date | None, sex: str | None, birth_entity: str | None
) -> list[str]:
    """Differences between the CURP and the captured fields (empty list = coherent)."""
    problems = []
    if birth_date is not None and birth_date != data.birth_date:
        problems.append(f"La fecha de nacimiento no coincide con la CURP ({data.birth_date}).")
    if sex is not None and sex != data.sex:
        problems.append(f"El sexo no coincide con la CURP ({data.sex}).")
    if birth_entity is not None and birth_entity != data.birth_entity:
        problems.append(f"La entidad de nacimiento no coincide con la CURP ({data.birth_entity}).")
    return problems


def mask(curp: str) -> str:
    """GODE561231HDFRRN09 → GODE******HDFRRN09 (birth date hidden)."""
    return curp[:4] + "******" + curp[10:] if len(curp) == 18 else "******"
