import { createHmac } from "node:crypto";
import { readFileSync } from "node:fs";
import { expect, type Page } from "@playwright/test";

export interface Seed {
  password: string;
  users: Record<
    "login" | "enroll" | "capture" | "substitute" | "scoped" | "geography",
    { email: string; totp_secret: string | null }
  >;
  process_id: string;
  municipality_1: string;
  people: { id: string; name: string; sex: string }[];
  substitute_candidate: { id: string; name: string };
  nominations: { local_district_1: string; local_district_2: string };
  seeded_formula: { owner: string; substitute: string };
}

export const seed: Seed = JSON.parse(
  readFileSync(new URL("./.seed.json", import.meta.url), "utf8"),
);

function base32(secret: string): Buffer {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const char of secret.replace(/=+$/, ""))
    bits += alphabet.indexOf(char).toString(2).padStart(5, "0");
  const bytes = bits.match(/.{8}/g) ?? [];
  return Buffer.from(bytes.map((b) => Number.parseInt(b, 2)));
}

/** RFC 6238 TOTP (SHA-1, 30 s, 6 digits), as Google Authenticator computes it. */
export function totp(secret: string, at = Date.now()): string {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 1000 / 30)));
  const hmac = createHmac("sha1", base32(secret)).update(counter).digest();
  const offset = (hmac[hmac.length - 1] ?? 0) & 0x0f;
  const code = (hmac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000;
  return code.toString().padStart(6, "0");
}

/** Password + TOTP through the real login screen. */
export async function login(page: Page, user: keyof Seed["users"]) {
  const account = seed.users[user];
  await page.goto("/login");
  await page.getByLabel("Correo").fill(account.email);
  await page.getByLabel("Contraseña").fill(seed.password);
  await page.getByRole("button", { name: "Entrar" }).click();
  if (account.totp_secret) {
    await expect(page.getByRole("heading", { name: "Segundo factor" })).toBeVisible();
    await page.getByLabel("Código").fill(totp(account.totp_secret));
    await page.getByRole("button", { name: "Verificar" }).click();
    await expect(page.getByRole("heading", { name: "Panel de administración" })).toBeVisible();
  }
}

/** Pick a person in an autocomplete by typing part of the name (keyboard only). */
export async function pickWithKeyboard(page: Page, comboboxName: string | RegExp, text: string) {
  // The trigger button (the popover's search input is also a combobox).
  const combobox = page.getByRole("combobox", { name: comboboxName }).and(page.locator("button"));
  await combobox.focus();
  await page.keyboard.type(text, { delay: 20 });
  const option = page.getByRole("option").filter({ hasText: text }).first();
  await expect(option).toBeVisible();
  await expect(option).toHaveAttribute("data-selected", "true");
  await page.keyboard.press("Enter");
  await expect(combobox).toContainText(text);
}
