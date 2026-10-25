import { expect, test } from "@playwright/test";

test("renders the shell and reports system status", async ({ page }) => {
  await page.route("**/ready", (route) =>
    route.fulfill({ json: { status: "ok", database: "ok", redis: "ok" } }),
  );
  await page.goto("/");

  await expect(page).toHaveTitle(/PAZOS/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Panel de administración" }),
  ).toBeVisible();
  await expect(page.getByRole("list", { name: "Dependencias" })).toContainText("Base de datos");
});

test("skip link is the first focusable element", async ({ page }) => {
  await page.route("**/ready", (route) =>
    route.fulfill({ json: { status: "ok", database: "ok", redis: "ok" } }),
  );
  await page.goto("/");
  await page.getByRole("heading", { level: 1 }).waitFor();
  await page.locator("body").press("Tab");
  await expect(page.getByRole("link", { name: "Saltar al contenido" })).toBeFocused();
});
