import type { QueryClient } from "@tanstack/react-query";
import { createRootRouteWithContext, Link, Outlet } from "@tanstack/react-router";
import { lazy, Suspense } from "react";

export interface RouterContext {
  queryClient: QueryClient;
}

const Devtools = import.meta.env.DEV
  ? lazy(() =>
      import("@tanstack/react-router-devtools").then((m) => ({
        default: m.TanStackRouterDevtools,
      })),
    )
  : () => null;

export const Route = createRootRouteWithContext<RouterContext>()({
  component: RootLayout,
  notFoundComponent: () => <p className="p-6">Página no encontrada.</p>,
});

function RootLayout() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <a
        href="#contenido"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50"
      >
        Saltar al contenido
      </a>
      <header className="border-b">
        <nav aria-label="Principal" className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4">
          <Link to="/" className="font-semibold tracking-tight">
            PAZOS
          </Link>
        </nav>
      </header>
      <main id="contenido" className="mx-auto max-w-6xl px-4 py-8">
        <Outlet />
      </main>
      <Suspense>
        <Devtools position="bottom-right" />
      </Suspense>
    </div>
  );
}
