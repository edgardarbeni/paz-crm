import { expect, test } from "@playwright/test";
import { login } from "./support";

test("the map loads the base map and the scoped electoral tiles with the user's token", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("console", (message) => message.type() === "error" && errors.push(message.text()));
  await login(page, "geography");
  const tile = page.waitForResponse((response) =>
    response.url().includes("/api/v1/geography/tiles/states/"),
  );
  await page.goto("/geography/map");
  expect((await tile).status()).toBe(200);
  await expect(page.getByRole("region", { name: "Mapa de geografía electoral" })).toBeVisible();
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
  expect(errors.filter((e) => !e.includes("WebGL"))).toEqual([]);

  // Explorer → node detail with ancestors.
  await page.goto("/geography?level=municipality");
  await page.getByRole("table", { name: "Municipio" }).getByText("MUNICIPIO UNO").click();
  await expect(page.getByRole("heading", { level: 1, name: /MUNICIPIO UNO/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Pertenece a" })).toBeVisible();

  // "Contiene" lists the children in place: the short group opens by itself and leads to them.
  await expect(page.getByRole("heading", { name: "Contiene" })).toBeVisible();
  const sections = page.getByRole("button", { name: /Secciones/ });
  await expect(sections).toHaveAttribute("aria-expanded", "true");
  await expect(sections).toContainText("4");
  await page.getByRole("link", { name: "Sección 0101" }).click();
  await expect(page.getByRole("heading", { level: 1, name: /01-0101/ })).toBeVisible();
});
