import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { locatePointOptions } from "@/client/@tanstack/react-query.gen";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AncestorsList } from "@/features/geography/ancestors-list";

export const Route = createFileRoute("/_app/geography/locate")({ component: LocatePage });

/** Point-in-polygon (D-19): accepts "lat, lon" pasted from any map. */
function LocatePage() {
  const [text, setText] = useState("");
  const [point, setPoint] = useState<{ lat: number; lon: number } | null>(null);
  const [invalid, setInvalid] = useState(false);
  const located = useQuery({
    ...locatePointOptions({ query: point ?? { lat: 0, lon: 0 } }),
    enabled: !!point,
  });
  return (
    <section className="max-w-xl">
      <PageHeader
        title="Ubicar coordenada"
        description="Devuelve la sección, municipio, distritos, estado y circunscripción de un punto."
      />
      <Card>
        <CardContent className="space-y-4">
          <form
            className="flex items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              const [lat, lon] = text
                .split(/[,\s]+/)
                .filter(Boolean)
                .map(Number);
              const ok =
                lat !== undefined &&
                lon !== undefined &&
                Math.abs(lat) <= 90 &&
                Math.abs(lon) <= 180 &&
                !Number.isNaN(lat + lon);
              setInvalid(!ok);
              if (ok) setPoint({ lat, lon });
            }}
          >
            <div className="grid flex-1 gap-1.5">
              <Label htmlFor="coords">Latitud, longitud</Label>
              <Input
                id="coords"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="21.8818, -102.2916"
                autoFocus
                aria-invalid={invalid}
                aria-describedby={invalid ? "coords-error" : undefined}
              />
            </div>
            <Button type="submit">Ubicar</Button>
          </form>
          {invalid ? (
            <p id="coords-error" role="alert" className="text-sm text-destructive">
              Escribe latitud y longitud separadas por coma.
            </p>
          ) : null}
          <ProblemAlert error={located.error} />
          {located.data ? <AncestorsList ancestors={located.data} /> : null}
        </CardContent>
      </Card>
    </section>
  );
}
