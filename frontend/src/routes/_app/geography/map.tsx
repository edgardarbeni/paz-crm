import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { locatePointOptions } from "@/client/@tanstack/react-query.gen";
import { LabeledToggle } from "@/components/labeled-toggle";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Card, CardContent } from "@/components/ui/card";
import { AncestorsList } from "@/features/geography/ancestors-list";
import { ELECTORAL_LAYERS, GeoMap, type LayerId } from "@/features/geography/geo-map";

export const Route = createFileRoute("/_app/geography/map")({ component: MapPage });

function MapPage() {
  const [visible, setVisible] = useState<LayerId[]>(["states", "municipalities", "sections"]);
  const [point, setPoint] = useState<{ lng: number; lat: number } | null>(null);
  const located = useQuery({
    ...locatePointOptions({ query: { lat: point?.lat ?? 0, lon: point?.lng ?? 0 } }),
    enabled: !!point,
  });
  return (
    <section>
      <PageHeader
        title="Mapa"
        description="Capas electorales del marco activo sobre el mapa base. Haz clic en el mapa para saber a qué sección pertenece el punto."
      />
      <div className="grid gap-4 lg:grid-cols-[1fr_18rem]">
        <GeoMap visible={visible} onClick={setPoint} />
        <div className="space-y-4">
          <Card>
            <CardContent>
              <fieldset className="space-y-2">
                <legend className="mb-2 text-sm font-medium">Capas</legend>
                {ELECTORAL_LAYERS.map((layer) => (
                  <LabeledToggle
                    key={layer.id}
                    checked={visible.includes(layer.id)}
                    onCheckedChange={(checked) =>
                      setVisible(
                        checked ? [...visible, layer.id] : visible.filter((id) => id !== layer.id),
                      )
                    }
                  >
                    <span aria-hidden className="h-0.5 w-4" style={{ background: layer.color }} />
                    {layer.label}
                    {layer.minzoom > 4 ? (
                      <span className="text-xs text-muted-foreground">
                        (zoom ≥ {layer.minzoom})
                      </span>
                    ) : null}
                  </LabeledToggle>
                ))}
              </fieldset>
            </CardContent>
          </Card>
          {point ? (
            <Card>
              <CardContent className="space-y-2 text-sm">
                <p className="text-xs text-muted-foreground">
                  {point.lat.toFixed(5)}, {point.lng.toFixed(5)}
                </p>
                <ProblemAlert error={located.error} />
                {located.data ? <AncestorsList ancestors={located.data} /> : null}
                {located.data ? (
                  <Link
                    to="/geography/$level/$nodeId"
                    params={{ level: "section", nodeId: located.data.section.id }}
                    className="underline"
                  >
                    Ver sección
                  </Link>
                ) : null}
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </section>
  );
}
