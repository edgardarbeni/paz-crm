import { describe, expect, it } from "vitest";
import { z } from "zod";
import { hasPermission, Perm } from "@/lib/auth/permissions";
import { blanksToNull, configureZod, formSchema } from "@/lib/forms";
import { formatDate, options, SEX_LABELS } from "@/lib/labels";

describe("form helpers", () => {
  it("turns blank strings into null, deeply, and trims the rest", () => {
    expect(blanksToNull({ a: " ", b: " x ", c: [{ d: "" }], e: 3, f: false })).toEqual({
      a: null,
      b: "x",
      c: [{ d: null }],
      e: 3,
      f: false,
    });
  });

  it("validates generated schemas with blanks as null and Spanish messages", async () => {
    configureZod();
    const schema = formSchema(
      z.object({ curp: z.string().min(18).nullish(), name: z.string().min(1) }),
    );
    const ok = await schema["~standard"].validate({ curp: "", name: "Ana" });
    expect(ok.issues).toBeUndefined();
    const bad = await schema["~standard"].validate({ curp: "CORTA", name: "Ana" });
    expect(bad.issues?.[0]?.message).toMatch(/demasiado|caracteres/i);
  });

  it("checks permissions, with grants_all as wildcard", () => {
    expect(
      hasPermission({ grants_all: false, permissions: [Perm.PERSON_READ] }, Perm.PERSON_READ),
    ).toBe(true);
    expect(hasPermission({ grants_all: false, permissions: [] }, Perm.PERSON_READ)).toBe(false);
    expect(hasPermission({ grants_all: true, permissions: [] }, Perm.RULE_OVERRIDE)).toBe(true);
    expect(hasPermission(undefined, Perm.PERSON_READ)).toBe(false);
  });

  it("formats labels and dates for es-MX", () => {
    expect(options(SEX_LABELS)).toContainEqual({ value: "M", label: "Mujer" });
    expect(formatDate("2027-06-06")).toMatch(/6 jun 2027/);
    expect(formatDate(null)).toBe("—");
  });
});
