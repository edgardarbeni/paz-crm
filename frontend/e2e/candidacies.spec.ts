import { expect, test } from "@playwright/test";
import { login, pickWithKeyboard, seed } from "./support";

test("capture a complete municipal slate with the keyboard and submit it", async ({ page }) => {
  await login(page, "capture");
  await page.goto(`/nominations/new?process_id=${seed.process_id}`);
  await page.getByLabel("Cargo").selectOption({ label: "Presidencia municipal" });
  await pickWithKeyboard(page, /Buscar municipio/, "MUNICIPIO UNO");
  await page.getByLabel("Partido que postula").selectOption({ label: "PAZ — PAZ" });
  await page.getByRole("button", { name: "Crear y capturar fórmulas" }).click();

  await expect(
    page.getByRole("heading", { level: 1, name: "Presidencia municipal" }),
  ).toBeVisible();
  // 1 presidency + 1 syndic + 2 MR + 1 RP councilors, from the municipality settings.
  const positions = [
    ["Presidencia municipal 1", 0],
    ["Sindicatura 1", 2],
    ["Regiduría de mayoría relativa 1", 4],
    ["Regiduría de mayoría relativa 2", 6],
    ["Regiduría de representación proporcional 1", 8],
  ] as const;
  for (const [label, index] of positions) {
    const owner = seed.people[index];
    const substitute = seed.people[index + 1];
    if (!owner || !substitute) throw new Error("seed has too few people");
    await pickWithKeyboard(page, `Propietaria · ${label}`, owner.name);
    await pickWithKeyboard(page, `Suplente · ${label}`, substitute.name);
    await page.keyboard.press("Control+Enter");
    await expect(page.getByRole("listitem").filter({ hasText: owner.name })).toContainText(
      "Aspirante",
    );
  }
  await expect(page.getByText("Todas las posiciones están capturadas.")).toBeVisible();

  // The same person twice in the process is blocked by the default rule.
  await page.getByRole("tab", { name: "Validación" }).click();
  await expect(page.getByText("Cumple todas las reglas activas")).toBeVisible();
  await page.getByRole("tab", { name: "Fórmulas" }).click();

  await page.getByRole("button", { name: "Enviar" }).click();
  await expect(page.getByText("Enviada", { exact: true })).toBeVisible();
  await expect(page.getByRole("combobox", { name: /Propietaria/ })).toHaveCount(0);
});

test("substitute a formula: new formula in the same position, history keeps both", async ({
  page,
}) => {
  await login(page, "substitute");
  await page.goto(`/nominations/${seed.nominations.local_district_1}`);
  const row = page.getByRole("listitem").filter({ hasText: seed.seeded_formula.owner });
  await row.getByRole("button", { name: /Acciones de la posición 1/ }).click();
  await page.getByRole("menuitem", { name: "Sustituir…" }).click();

  const dialog = page.getByRole("dialog", { name: /Sustituir la fórmula/ });
  await dialog.getByLabel("Motivo de la sustitución").fill("Renuncia presentada ante el consejo");
  await dialog.getByRole("button", { name: /Quitar Propietaria/ }).click();
  await pickWithKeyboard(page, /Propietaria · posición 1/, seed.substitute_candidate.name);
  await dialog.getByRole("button", { name: "Sustituir" }).click();
  await expect(dialog).toBeHidden();

  await expect(
    page.getByRole("listitem").filter({ hasText: seed.substitute_candidate.name }),
  ).toBeVisible();
  await expect(page.getByText(seed.seeded_formula.owner)).toHaveCount(0);
  await page.getByRole("tab", { name: "Historial" }).click();
  const history = page.getByRole("table", { name: "Historial de estatus" });
  await expect(history).toContainText("Aspirante → Sustituida");
  await expect(history).toContainText("Renuncia presentada ante el consejo");
});

test("a coordinator limited to one municipality: read-only beyond the scope, invisible outside it", async ({
  page,
}) => {
  await login(page, "scoped");
  await page.goto("/nominations");
  const table = page.getByRole("table", { name: "Postulaciones" });
  await expect(table).toContainText("Distrito local");
  const rows = table.getByRole("row");
  // District 2 (sections of municipality 2 only) is not listed; district 1 overlaps the scope.
  await expect(rows.filter({ hasText: "Distrito local 01-01" })).toHaveCount(1);
  await expect(rows.filter({ hasText: "Distrito local 01-02" })).toHaveCount(0);

  await page.goto(`/nominations/${seed.nominations.local_district_1}`);
  await expect(page.getByText("Solo lectura (fuera de tu alcance)")).toBeVisible();
  await expect(page.getByRole("button", { name: /Acciones de la posición/ })).toHaveCount(0);

  await page.goto(`/nominations/${seed.nominations.local_district_2}`);
  await expect(page.getByRole("alert")).toContainText("no encontrada");

  // Geography is limited too: only the municipality in scope.
  await page.goto("/geography?level=municipality");
  const municipalities = page.getByRole("table", { name: "Municipio" });
  await expect(municipalities).toContainText("MUNICIPIO UNO");
  await expect(municipalities).not.toContainText("MUNICIPIO DOS");
});
