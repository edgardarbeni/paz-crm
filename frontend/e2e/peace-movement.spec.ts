import { expect, test } from "@playwright/test";
import { login, pickWithKeyboard, seed } from "./support";

test("Movimiento de Paz: validar, inscribir, ver la red y las integraciones del panel", async ({
  page,
}) => {
  await login(page, "peace");

  // The validation queue lists the pending enrollment; validating it removes it.
  await page.getByRole("link", { name: "Validación" }).click();
  await expect(page.getByRole("heading", { name: "Validación de inscripciones" })).toBeVisible();
  const pending = page.getByRole("listitem").filter({ hasText: seed.peace.pending.name });
  await pending.getByRole("button", { name: "Validar" }).click();
  await expect(page.getByText(`${seed.peace.pending.name} validado.`)).toBeVisible();
  await expect(page.getByText("No hay inscripciones pendientes.")).toBeVisible();

  // Enroll a recruit of the Ambassador from her profile.
  await page.goto(`/peace-movement/members/${seed.peace.root.id}`);
  await expect(page.getByRole("heading", { level: 1, name: seed.peace.root.name })).toBeVisible();
  await expect(page.getByRole("img", { name: /QR de inscripción/ })).toBeVisible();
  await page.getByRole("link", { name: "Inscribir recluta" }).click();
  await expect(page.getByRole("heading", { name: "Inscribir pacificador" })).toBeVisible();
  await page.getByLabel("Nombre(s)").fill("Wendy");
  await page.getByLabel("Primer apellido").fill("Nueva");
  await page.getByLabel("CURP").fill(seed.peace.next_curp);
  await page.getByLabel("Calle").fill("Avenida Paz 10");
  await pickWithKeyboard(page, "Sección electoral", "101", "Sección 0101");
  await expect(page.getByRole("combobox", { name: "Reclutador" })).toContainText(
    seed.peace.root.name,
  );
  await page.getByRole("button", { name: "Inscribir" }).click();
  await expect(page.getByRole("heading", { level: 1, name: /Wendy Nueva/ })).toBeVisible();
  await expect(page.getByText("Activo", { exact: true })).toBeVisible();

  // Back at the Ambassador: the new recruit is listed among her direct recruits.
  await page.getByRole("link", { name: seed.peace.root.name }).click();
  await expect(page.getByRole("table", { name: "Reclutas directos" })).toContainText("Wendy Nueva");

  // The person's profile shows their Peace Movement membership and links to it.
  await page.goto(`/people/${seed.peace.root.person_id}`);
  const card = page.locator('[data-slot="card"]').filter({
    has: page.getByRole("heading", { name: "Movimiento de Paz" }),
  });
  await expect(card).toContainText("Activo");
  await expect(page.getByRole("link", { name: "Inscribir en el Movimiento de Paz" })).toHaveCount(
    0,
  );
  await card.getByRole("link", { name: "Embajador de Paz" }).click();
  await expect(page.getByRole("heading", { level: 1, name: seed.peace.root.name })).toBeVisible();

  // Opening the member profile is a sensitive read (D-89), listed in its own audit tab.
  await page.goto("/audit");
  await page.getByRole("tab", { name: "Lecturas sensibles" }).click();
  await expect(page.getByRole("table", { name: "Lecturas sensibles" })).toContainText("Consulta");

  // The houses map lives in the panel (D-100).
  await page.goto("/peace-movement/houses");
  await page.getByRole("link", { name: "Ver mapa" }).click();
  await expect(page.getByRole("heading", { name: "Mapa de Casas de Paz" })).toBeVisible();
  await expect(page.getByText(/\d+ casas/)).toBeVisible();

  // D-103: the tray of houses to link; without a structure seat there is nothing to link with.
  await page.getByRole("link", { name: "Casas por enlazar" }).click();
  await expect(page.getByRole("heading", { name: "Casas por enlazar" })).toBeVisible();
  await expect(page.getByText("No ocupas ningún cargo de la estructura")).toBeVisible();
});

test("la página pública de inscripción resuelve la verificación y recibe la inscripción", async ({
  page,
}) => {
  await page.goto(`/inscripcion/${seed.peace.root.code}`);
  await expect(page.getByRole("heading", { name: "Súmate al Movimiento de Paz" })).toBeVisible();
  await page.getByLabel("Nombre(s)").fill("Ximena");
  await page.getByLabel("Primer apellido").fill("Pública");
  await page.getByLabel("CURP").fill("AAAA000000HXXXXX00");
  // An invalid CURP blocks the submit; a valid one enables it.
  await expect(page.getByRole("alert")).toBeVisible();
  await page.getByLabel("CURP").fill(seed.peace.public_curp);
  await page.getByLabel("Celular (10 dígitos)").fill("4491234500");
  await page.getByLabel("Entidad").selectOption({ label: "Aguascalientes" });
  await page.getByLabel("Sección").fill("102");
  await page.getByLabel(/Leí y acepto/).check();
  const submit = page.getByRole("button", { name: "Inscribirme" });
  await expect(submit).toBeEnabled({ timeout: 30_000 }); // proof of work solved
  await page.waitForTimeout(3_100); // the server asks for a minimum fill time
  await submit.click();
  await expect(page.getByRole("heading", { name: "¡Gracias por sumarte!" })).toBeVisible();
});
