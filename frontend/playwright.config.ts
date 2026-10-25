import { defineConfig, devices } from "@playwright/test";

// End-to-end tests against the real stack: run them with ./scripts/e2e.sh, which starts
// PostgreSQL/PostGIS, Redis, the seeded API and then this config (production build served by
// `vite preview`, proxying /api). Each scenario uses its own seeded user (TOTP anti-replay).
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  timeout: 60_000,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: { baseURL: "http://localhost:4173", trace: "retain-on-failure", locale: "es-MX" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "pnpm build && pnpm preview",
    url: "http://localhost:4173/login",
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    env: { VITE_DEV_API_PROXY: process.env.VITE_DEV_API_PROXY ?? "http://127.0.0.1:8010" },
  },
});
