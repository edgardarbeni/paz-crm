import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { List } from "lucide-react";
import { z } from "zod";
import { getPeaceHousesMapOptions } from "@/client/@tanstack/react-query.gen";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { GeoMap, type PointCollection } from "@/features/geography/geo-map";
import { HOUSE_STATUS, SELECT_CLASS } from "@/features/peace-movement/labels";

const STATUSES = ["open", "consolidated", "closed"] as const;
const LEGEND: [string, string][] = [
  ["consolidated", "bg-[#682575]"],
  ["open", "bg-[#d97706]"],
  ["closed", "bg-[#94a3b8]"],
];

export const Route = createFileRoute("/_app/peace-movement/houses/map")({
  validateSearch: z.object({ status: z.enum(STATUSES).optional() }),
  component: HousesMapPage,
});

/** Peace Houses on the map, inside the panel (D-100). Points are the approximate location
 * (~100 m, D-85); the exact one stays encrypted. */
function HousesMapPage() {
  const { status } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const houses = useQuery(getPeaceHousesMapOptions({ query: status ? { status } : {} }));
  const count = houses.data?.features.length ?? 0;
  return (
    <section className="space-y-4">
      <PageHeader
        title="Mapa de Casas de Paz"
        description="Ubicación aproximada (unos 100 m) de las casas dentro de tu alcance. Haz clic en un grupo para acercarte y en una casa para abrirla."
        actions={
          <Button asChild variant="outline">
            <Link to="/peace-movement/houses">
              <List aria-hidden /> Ver lista
            </Link>
          </Button>
        }
      />
      <div className="flex flex-wrap items-end gap-4">
        <div className="grid gap-1.5">
          <Label htmlFor="map-status">Estatus</Label>
          <select
            id="map-status"
            className={SELECT_CLASS}
            value={status ?? ""}
            onChange={(event) =>
              navigate({
                search: {
                  status: (event.target.value || undefined) as (typeof STATUSES)[number],
                },
              })
            }
          >
            <option value="">Abiertas y consolidadas</option>
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {HOUSE_STATUS[value]}
              </option>
            ))}
          </select>
        </div>
        <ul className="flex flex-wrap gap-3 text-sm" aria-label="Simbología">
          {LEGEND.map(([value, color]) => (
            <li key={value} className="flex items-center gap-1.5">
              <span aria-hidden className={`size-3 rounded-full ring-2 ring-white ${color}`} />
              {HOUSE_STATUS[value]}
            </li>
          ))}
        </ul>
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {houses.isPending ? "Cargando…" : `${count} casas`}
        </p>
      </div>
      <ProblemAlert error={houses.error} />
      {houses.data?.truncated ? (
        <Alert>
          <AlertDescription>
            Hay más casas de las que se muestran; filtra por estatus para ver el resto.
          </AlertDescription>
        </Alert>
      ) : null}
      <GeoMap
        visible={["states", "municipalities"]}
        points={(houses.data as PointCollection | undefined) ?? null}
        fitPoints
        onPointClick={(properties) =>
          navigate({
            to: "/peace-movement/houses/$houseId",
            params: { houseId: String(properties.id) },
          })
        }
        className="h-[70vh] w-full rounded-lg border"
      />
    </section>
  );
}
