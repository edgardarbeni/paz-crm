/**
 * CURP check in the browser, same rules as the backend (`app/modules/people/curp.py`, D-30):
 * structure, RENAPO check digit, real birth date. Used for inline validation only; the API
 * validates again.
 */
const ALPHABET = "0123456789ABCDEFGHIJKLMNÑOPQRSTUVWXYZ";
export const CURP_ENTITIES = [
  "AS",
  "BC",
  "BS",
  "CC",
  "CL",
  "CM",
  "CS",
  "CH",
  "DF",
  "DG",
  "GT",
  "GR",
  "HG",
  "JC",
  "MC",
  "MN",
  "MS",
  "NT",
  "NL",
  "OC",
  "PL",
  "QT",
  "QR",
  "SP",
  "SL",
  "SR",
  "TC",
  "TS",
  "TL",
  "VZ",
  "YN",
  "ZS",
  "NE",
] as const;

const PATTERN = new RegExp(
  "^[A-Z][AEIOUX][A-Z]{2}\\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\\d|3[01])[HMX]" +
    `(${CURP_ENTITIES.join("|")})[B-DF-HJ-NP-TV-Z]{3}[0-9A-Z]\\d$`,
);

export interface CurpData {
  curp: string;
  birthDate: string; // YYYY-MM-DD
  sex: "H" | "M" | "X";
  birthEntity: string;
}

export function normalizeCurp(value: string): string {
  return value.replace(/\s+/g, "").toUpperCase();
}

export function curpCheckDigit(first17: string): string {
  let total = 0;
  for (let i = 0; i < 17; i++) total += ALPHABET.indexOf(first17[i] ?? "0") * (18 - i);
  return String((10 - (total % 10)) % 10);
}

export type CurpResult = { ok: true; data: CurpData } | { ok: false; error: string };

export function parseCurp(value: string): CurpResult {
  const curp = normalizeCurp(value);
  if (curp.length !== 18 || !PATTERN.test(curp)) {
    return { ok: false, error: "La CURP no tiene una estructura válida." };
  }
  if (curpCheckDigit(curp) !== curp[17]) {
    return { ok: false, error: "El dígito verificador de la CURP no corresponde." };
  }
  const century = /\d/.test(curp[16] ?? "") ? 1900 : 2000;
  const year = century + Number(curp.slice(4, 6));
  const month = Number(curp.slice(6, 8));
  const day = Number(curp.slice(8, 10));
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) {
    return { ok: false, error: "La fecha de nacimiento de la CURP no existe." };
  }
  return {
    ok: true,
    data: {
      curp,
      birthDate: date.toISOString().slice(0, 10),
      sex: curp[10] as CurpData["sex"],
      birthEntity: curp.slice(11, 13),
    },
  };
}

/** Differences between the CURP and captured fields (empty = coherent). */
export function curpCoherence(
  data: CurpData,
  fields: { birthDate?: string | null; sex?: string | null; birthEntity?: string | null },
): string[] {
  const problems: string[] = [];
  if (fields.birthDate && fields.birthDate !== data.birthDate)
    problems.push(`La fecha de nacimiento no coincide con la CURP (${data.birthDate}).`);
  if (fields.sex && fields.sex !== data.sex)
    problems.push(`El sexo no coincide con la CURP (${data.sex}).`);
  if (fields.birthEntity && fields.birthEntity !== data.birthEntity)
    problems.push(`La entidad de nacimiento no coincide con la CURP (${data.birthEntity}).`);
  return problems;
}
