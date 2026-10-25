import { createFileRoute } from "@tanstack/react-router";
import { Kbd, PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SystemStatus } from "@/features/system/system-status";
import { useMe } from "@/lib/auth/use-me";

export const Route = createFileRoute("/_app/")({ component: HomePage });

const SHORTCUTS: [string, string][] = [
  ["Ctrl K", "Ir a cualquier pantalla"],
  ["/", "Buscar en la lista actual"],
  ["N", "Nuevo registro (en listas)"],
  ["↑ ↓ / Enter", "Recorrer filas y abrir"],
  ["Ctrl Enter", "Guardar el formulario"],
  ["Esc", "Cerrar diálogos"],
];

function HomePage() {
  const me = useMe();
  return (
    <section aria-labelledby="titulo-inicio">
      <PageHeader
        title="Panel de administración"
        description={me ? `Hola, ${me.full_name}.` : undefined}
      />
      <div className="grid gap-6 lg:grid-cols-2">
        <SystemStatus />
        <Card>
          <CardHeader>
            <CardTitle>
              <h2>Atajos de teclado</h2>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
              {SHORTCUTS.map(([keys, label]) => (
                <div key={keys} className="contents">
                  <dt>
                    <Kbd>{keys}</Kbd>
                  </dt>
                  <dd>{label}</dd>
                </div>
              ))}
            </dl>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
