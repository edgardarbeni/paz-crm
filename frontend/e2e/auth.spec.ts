import { expect, test } from "@playwright/test";
import { login, seed, totp } from "./support";

test("unauthenticated visitors land on the login screen; skip link comes first", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await expect(page).toHaveTitle(/PAZOS/);
  // The email field is autofocused; the skip link is still the first stop in tab order.
  await expect(page.getByLabel("Correo")).toBeFocused();
  const first = await page.evaluate(
    () =>
      document.querySelector<HTMLElement>("a[href], button, input, select, textarea")?.textContent,
  );
  expect(first).toBe("Saltar al contenido");
  const skip = page.getByRole("link", { name: "Saltar al contenido" });
  await skip.focus();
  await expect(skip).toBeVisible();
});

test("login with password + TOTP, session survives a reload, logout ends it", async ({ page }) => {
  const account = seed.users.login;
  await page.goto("/login");
  await page.getByLabel("Correo").fill(account.email);
  await page.getByLabel("Contraseña").fill("incorrecta-de-verdad");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByRole("alert")).toContainText(/credenciales|correo o contraseña/i);

  await page.getByLabel("Contraseña").fill(seed.password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.getByLabel("Código").fill("000000");
  await page.getByRole("button", { name: "Verificar" }).click();
  await expect(page.getByRole("alert")).toBeVisible();

  await page.getByLabel("Código").fill(totp(account.totp_secret ?? ""));
  await page.getByRole("button", { name: "Verificar" }).click();
  await expect(page.getByRole("heading", { name: "Panel de administración" })).toBeVisible();

  // The access token lives in memory only; the refresh cookie restores the session.
  await page.reload();
  await expect(page.getByRole("heading", { name: "Panel de administración" })).toBeVisible();

  // Keyboard navigation: Ctrl+K opens the command palette.
  await page.keyboard.press("Control+k");
  await page.keyboard.type("Partidos");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Partidos" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Partidos" })).toContainText("PAZ");

  await page.getByRole("button", { name: "Cerrar sesión" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/parties");
  await expect(page).toHaveURL(/\/login/);
});

test("a role that requires 2FA enrolls TOTP on first login and gets recovery codes", async ({
  page,
}) => {
  await login(page, "enroll");
  await expect(page.getByRole("heading", { name: "Configura tu app autenticadora" })).toBeVisible();
  await expect(page.getByRole("img", { name: /Código QR/ })).toBeVisible();
  const secret = (await page.locator("code").first().textContent())?.trim() ?? "";
  expect(secret).toMatch(/^[A-Z2-7]{16,}$/);
  await page.getByLabel("Código").fill(totp(secret));
  await page.getByRole("button", { name: "Activar" }).click();
  await expect(
    page.getByRole("list", { name: "Códigos de recuperación" }).getByRole("listitem"),
  ).toHaveCount(10);
  await page.getByRole("button", { name: "Ya los guardé, continuar" }).click();
  await expect(page.getByRole("heading", { name: "Panel de administración" })).toBeVisible();
});
