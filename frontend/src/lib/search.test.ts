import { describe, expect, it } from "vitest";
import { geoChildLabel, geoNodeLabel } from "./search";

const base = { state_name: "AGUASCALIENTES", municipality_name: null };

describe("geoNodeLabel", () => {
  it("names every level by what it is and its state", () => {
    expect(
      geoNodeLabel({ ...base, level: "state", code: "1", key: "01", name: "AGUASCALIENTES" }),
    ).toEqual({ label: "AGUASCALIENTES", hint: "Estado · 01" });
    expect(
      geoNodeLabel({ ...base, level: "municipality", code: "3", key: "01-003", name: "CALVILLO" }),
    ).toEqual({ label: "CALVILLO · AGUASCALIENTES", hint: "Municipio · 01-003" });
    expect(
      geoNodeLabel({ ...base, level: "federal_district", code: "3", key: "01-03", name: null })
        .label,
    ).toBe("Distrito federal 03 · AGUASCALIENTES");
    expect(
      geoNodeLabel({ ...base, level: "local_district", code: "12", key: "01-12", name: null })
        .label,
    ).toBe("Distrito local 12 · AGUASCALIENTES");
  });

  it("shows the section number without the state prefix, with its municipality", () => {
    expect(
      geoNodeLabel({
        ...base,
        municipality_name: "CALVILLO",
        level: "section",
        code: "338",
        key: "01-0338",
        name: null,
      }),
    ).toEqual({ label: "Sección 0338 · AGUASCALIENTES", hint: "CALVILLO · Clave 01-0338" });
  });

  it("tells repeated colonia names apart by municipality", () => {
    expect(
      geoNodeLabel({
        ...base,
        municipality_name: "CALVILLO",
        level: "neighborhood",
        code: "11",
        key: "01-COL-11",
        name: "CENTRO",
      }),
    ).toEqual({ label: "CENTRO · AGUASCALIENTES", hint: "Colonia · CALVILLO · 01-COL-11" });
    expect(
      geoNodeLabel({ ...base, level: "locality", code: "1", key: "01-003-0001", name: null }).label,
    ).toBe("Sin nombre · AGUASCALIENTES");
  });
});

describe("geoChildLabel", () => {
  it("shows only the node's own number and name inside its parent", () => {
    expect(geoChildLabel({ level: "municipality", code: "4", name: "TIJUANA" })).toEqual({
      code: "004",
      label: "TIJUANA",
    });
    expect(geoChildLabel({ level: "federal_district", code: "5", name: null })).toEqual({
      code: null,
      label: "Distrito 05",
    });
    expect(geoChildLabel({ level: "section", code: "338", name: null })).toEqual({
      code: null,
      label: "Sección 0338",
    });
    expect(geoChildLabel({ level: "locality", code: "12", name: null })).toEqual({
      code: "0012",
      label: "Sin nombre",
    });
    expect(geoChildLabel({ level: "neighborhood", code: "P15", name: "CENTRO" })).toEqual({
      code: null,
      label: "CENTRO",
    });
  });
});
