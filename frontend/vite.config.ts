import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the panel is served behind Caddy (https://localhost), so API calls are
// same-origin. When running Vite alone, /api and health checks are proxied to the API.
const apiProxy = {
  "/api": process.env.VITE_DEV_API_PROXY ?? "http://localhost:8000",
  "/health": process.env.VITE_DEV_API_PROXY ?? "http://localhost:8000",
  "/ready": process.env.VITE_DEV_API_PROXY ?? "http://localhost:8000",
};

export default defineConfig({
  plugins: [tanstackRouter({ target: "react", autoCodeSplitting: true }), react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "src") },
  },
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    allowedHosts: ["localhost", "frontend"],
    proxy: apiProxy,
  },
  // E2E (scripts/e2e.sh) serve the production build and proxy the API the same way.
  preview: { port: 4173, strictPort: true, proxy: apiProxy },
  // MapLibre (~1 MB) only loads with the map screens (route code splitting).
  build: { sourcemap: true, chunkSizeWarningLimit: 1200 },
  // Module workers (MapLibre's worker is an ES module).
  worker: { format: "es" },
});
