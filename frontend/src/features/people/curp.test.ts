import { describe, expect, it } from "vitest";
import { curpCheckDigit, curpCoherence, parseCurp } from "./curp";

const build = (prefix: string) => prefix + curpCheckDigit(prefix);

describe("CURP", () => {
  it("accepts the documented vector and decodes it", () => {
    const result = parseCurp("boxw310820hnerxn09");
    expect(result).toEqual({
      ok: true,
      data: { curp: "BOXW310820HNERXN09", birthDate: "1931-08-20", sex: "H", birthEntity: "NE" },
    });
  });

  it("matches the backend check digit (same vectors as test_curp.py)", () => {
    expect(curpCheckDigit("BOXW310820HNERXN0")).toBe("9");
    expect(build("GALM850315MASRPR0")).toBe("GALM850315MASRPR03");
  });

  it("uses the 2000s for letter differentiators", () => {
    const result = parseCurp(build("GOME050101MASRRNA"));
    expect(result.ok && result.data.birthDate).toBe("2005-01-01");
  });

  it.each([
    ["XXXX", "estructura"],
    ["GOME050101MZZRRNA1", "estructura"],
    ["BOXW310820HNERXN08", "verificador"],
    [build("GOME050230MASRRNA"), "no existe"],
  ])("rejects %s", (value, message) => {
    const result = parseCurp(value);
    expect(result.ok).toBe(false);
    expect(!result.ok && result.error).toContain(message);
  });

  it("reports incoherent captured data", () => {
    const result = parseCurp("BOXW310820HNERXN09");
    if (!result.ok) throw new Error("expected a valid CURP");
    expect(curpCoherence(result.data, { birthDate: "1931-08-20", sex: "H" })).toEqual([]);
    expect(
      curpCoherence(result.data, { birthDate: "1931-08-21", sex: "M", birthEntity: "AS" }),
    ).toHaveLength(3);
  });
});
