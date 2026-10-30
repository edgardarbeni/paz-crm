import { expect, test } from "@playwright/test";
import { login, seed } from "./support";

test("concesiones: un rol con su alcance se agrega y se quita en la ficha del usuario", async ({
  page,
}) => {
  await login(page, "grants");
  await page.goto(`/users/${seed.users.target.id}`);
  await expect(page.getByRole("heading", { name: "Concesiones (rol y alcance)" })).toBeVisible();
  await expect(page.getByRole("listitem", { name: "Concesión Consulta" })).toContainText(
    "Sin alcance",
  );

  await page.getByLabel("Nueva concesión: rol").selectOption({ label: "Capturista" });
  // Read-only grants render no scope controls: these belong to the new grant.
  await page.getByLabel("Nivel del alcance").selectOption("national");
  await page.getByRole("button", { name: "Agregar alcance" }).click();
  await page.getByRole("button", { name: "Agregar concesión" }).click();
  await expect(page.getByText("Concesiones actualizadas.")).toBeVisible();
  const added = page.getByRole("listitem", { name: "Concesión Capturista" });
  await expect(added).toContainText("Todo el país");
  await expect(added).toContainText("Manual");

  await added.getByRole("button", { name: "Quitar Capturista" }).click();
  await page.getByRole("button", { name: "Quitar", exact: true }).click();
  await expect(page.getByRole("listitem", { name: "Concesión Capturista" })).toHaveCount(0);
});
