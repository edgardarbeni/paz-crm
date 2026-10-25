import "./index.css";
import { QueryClientProvider } from "@tanstack/react-query";
import { createRouter, RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { configureApiClient } from "@/lib/api";
import { onSessionExpiredHandler } from "@/lib/auth/session";
import { configureZod } from "@/lib/forms";
import { createQueryClient } from "@/lib/query-client";
import { routeTree } from "./routeTree.gen";

configureZod();
configureApiClient();
const queryClient = createQueryClient();
const router = createRouter({ routeTree, context: { queryClient }, defaultPreload: "intent" });

// Refresh failed (expired or revoked session): back to login, keeping where the user was.
onSessionExpiredHandler(() => {
  queryClient.clear();
  router.navigate({ to: "/login", search: { redirect: router.state.location.href } });
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

const root = document.getElementById("root");
if (!root) throw new Error("#root element not found");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
