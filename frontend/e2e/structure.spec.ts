import { expect, test } from "@playwright/test";
import { login, pickWithKeyboard, seed } from "./support";

test("estructura: nombrar en un órgano, crear una coordinación y ver el catálogo", async ({
  page,
}) => {
  await login(page, "structure");

  // Bodies: the national committee is seeded; appoint its Secretaría Jurídica.
  await page.getByRole("link", { name: "Órganos y cargos" }).click();
  await expect(page.getByRole("heading", { name: "Órganos y cargos" })).toBeVisible();
  await page.getByLabel("Nivel").selectOption("national");
  await page.getByRole("row", { name: /Comité Directivo Nacional/ }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Comité Directivo Nacional" }),
  ).toBeVisible();
  const seat = page.getByRole("listitem", { name: "Secretaría Jurídica" });
  await expect(seat).toContainText("Vacante");
  await seat.getByRole("button", { name: "Nombrar" }).click();
  await pickWithKeyboard(page, "Persona", "Rosa", seed.peace.root.name);
  await page.getByLabel("Acuerdo").fill("CN/001/2026");
  await page.getByRole("button", { name: "Nombrar", exact: true }).last().click();
  await expect(page.getByText(`${seed.peace.root.name} nombrado.`)).toBeVisible();
  await expect(seat).toContainText(seed.peace.root.name);
  await expect(seat).toContainText("Electo");

  // Coordinations: a sectional one with one section.
  await page.getByRole("link", { name: "Coordinaciones" }).click();
  await page.getByRole("button", { name: "Nueva coordinación" }).click();
  await page.getByLabel("Nombre").fill("Coordinación Centro E2E");
  // The territory picker adds a chip per node and clears itself.
  const territory = page
    .getByRole("combobox", { name: "Agregar territorio" })
    .and(page.locator("button"));
  await territory.focus();
  await page.keyboard.type("101", { delay: 20 });
  await expect(page.getByRole("option").filter({ hasText: "0101" }).first()).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("list", { name: "Territorio" })).toContainText("0101");
  await page.getByRole("button", { name: "Crear", exact: true }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Coordinación Centro E2E" }),
  ).toBeVisible();
  await expect(page.getByRole("listitem", { name: "Coordinación seccional" })).toContainText(
    "Vacante",
  );

  // The statutory catalog.
  await page.getByRole("link", { name: "Catálogo estatutario" }).click();
  await expect(page.getByRole("heading", { name: "Comité Directivo Nacional" })).toBeVisible();
  await expect(
    page.getByRole("list", { name: "Cargos de Comité Directivo Nacional" }),
  ).toContainText("Una por circunscripción");
});
