import { defineConfig } from "@hey-api/openapi-ts";

// Generated client (never edit by hand; CLAUDE.md forbids hand-written fetch calls).
// Regenerate with `pnpm gen:api` after any backend contract change.
export default defineConfig({
  input: "./openapi.json",
  output: { path: "src/client" },
  plugins: [
    "@hey-api/client-fetch",
    "@hey-api/typescript",
    "zod",
    { name: "@hey-api/sdk", validator: { response: true } },
    "@tanstack/react-query",
  ],
});
