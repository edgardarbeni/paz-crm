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
});
