import { useQuery } from "@tanstack/react-query";
import { getReadinessOptions } from "@/client/@tanstack/react-query.gen";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { problemMessage } from "@/lib/api";

const LABELS = {
  database: "Base de datos",
  redis: "Redis",
  storage: "Almacenamiento de archivos",
} as const;

const STATES: Record<string, string> = { ok: "Operando", disabled: "Sin configurar" };

export function SystemStatus() {
  const readiness = useQuery({ ...getReadinessOptions(), refetchInterval: 30_000 });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Estado del sistema</CardTitle>
        <CardDescription>Disponibilidad de la API y sus dependencias.</CardDescription>
      </CardHeader>
      <CardContent>
        {readiness.isPending && <p aria-live="polite">Verificando…</p>}
        {readiness.isError && (
          <p role="alert" className="text-destructive">
            {problemMessage(readiness.error)}
          </p>
        )}
        {readiness.isSuccess && (
          <ul className="space-y-2" aria-label="Dependencias">
            {(Object.keys(LABELS) as (keyof typeof LABELS)[]).map((key) => (
              <li key={key} className="flex items-center justify-between">
                <span>{LABELS[key]}</span>
                <Badge variant="secondary">{STATES[readiness.data[key]] ?? "Con fallas"}</Badge>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
