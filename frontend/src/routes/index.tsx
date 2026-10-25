import { createFileRoute } from "@tanstack/react-router";
import { SystemStatus } from "@/features/system/system-status";

export const Route = createFileRoute("/")({
  component: HomePage,
});

function HomePage() {
  return (
    <section aria-labelledby="titulo-inicio" className="space-y-6">
      <h1 id="titulo-inicio" className="text-2xl font-semibold tracking-tight">
        Panel de administración
      </h1>
      <SystemStatus />
    </section>
  );
}
