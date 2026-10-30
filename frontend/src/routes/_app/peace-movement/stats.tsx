import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Download } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import {
  getPeaceGeographyStatsOptions,
  getPeaceGrowthOptions,
} from "@/client/@tanstack/react-query.gen";
import { exportMembers } from "@/client/sdk.gen";
import type { GrowthPoint } from "@/client/types.gen";
import { AsyncCombobox, type ComboItem } from "@/components/async-combobox";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { formatCount, SELECT_CLASS } from "@/features/peace-movement/labels";
import { useLevels } from "@/features/peace-movement/shared";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";
import { formatDate, GEO_LEVEL_PLURALS } from "@/lib/labels";
import { GEO_SEARCH_HINTS, searchGeoItems } from "@/lib/search";

const LEVELS = ["state", "municipality", "federal_district", "local_district", "section"] as const;
type GeoLevel = (typeof LEVELS)[number];

export const Route = createFileRoute("/_app/peace-movement/stats")({
  validateSearch: z.object({
    level: z.enum(LEVELS).optional(),
    days: z.number().int().min(7).max(1095).optional(),
  }),
  component: StatsPage,
});

function isoDay(date: Date) {
  return date.toISOString().slice(0, 10);
}

function StatsPage() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  const can = useCan();
  const { levels } = useLevels();
  const level: GeoLevel = search.level ?? "state";
  const days = search.days ?? 90;
  const [state, setState] = useState<ComboItem | null>(null);
  const geography = useQuery(
    getPeaceGeographyStatsOptions({
      query: { level, ...(state && level !== "state" ? { state_id: state.id } : {}) },
    }),
  );
  const today = new Date();
  const from = new Date(today.getTime() - (days - 1) * 86_400_000);
  const growth = useQuery(
    getPeaceGrowthOptions({
      query: {
        from: isoDay(from),
        to: isoDay(today),
        ...(state ? { state_id: state.id } : {}),
      },
    }),
  );
  const total = geography.data?.reduce((sum, row) => sum + row.active, 0) ?? 0;
  const [exporting, setExporting] = useState(false);

  async function download() {
    setExporting(true);
    try {
      const { data, error } = await exportMembers({
        query: { status: "active", ...(state ? { state_id: state.id } : {}) },
        parseAs: "text",
      });
      if (error || typeof data !== "string") throw error ?? new Error("export");
      const url = URL.createObjectURL(new Blob([data], { type: "text/csv;charset=utf-8" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = `pacificadores-${isoDay(today)}.csv`;
      link.click();
      URL.revokeObjectURL(url);
      toast.success("Exportación lista. Queda registrada en la bitácora de lecturas.");
    } catch {
      toast.error("No se pudo exportar. Si son más de 50,000, acota por estado.");
    } finally {
      setExporting(false);
    }
  }

  return (
    <section className="max-w-6xl space-y-6">
      <PageHeader
        title="Estadísticas del Movimiento de Paz"
        description="Pacificadores activos e inscripciones validadas dentro de tu alcance. Las cifras se actualizan cada minuto."
        actions={
          can(Perm.PEACE_STATS_READ) ? (
            <Button variant="outline" onClick={download} disabled={exporting}>
              <Download aria-hidden /> {exporting ? "Exportando…" : "Exportar CSV"}
            </Button>
          ) : null
        }
      />
      <div className="flex flex-wrap items-end gap-3">
        <div className="grid gap-1.5">
          <Label htmlFor="stats-level">Agrupar por</Label>
          <select
            id="stats-level"
            className={SELECT_CLASS}
            value={level}
            onChange={(event) =>
              navigate({ search: (prev) => ({ ...prev, level: event.target.value as GeoLevel }) })
            }
          >
            {LEVELS.map((value) => (
              <option key={value} value={value}>
                {GEO_LEVEL_PLURALS[value] ?? value}
              </option>
            ))}
          </select>
        </div>
        <div className="grid w-72 gap-1.5">
          <Label htmlFor="stats-state">Estado</Label>
          <AsyncCombobox
            id="stats-state"
            label="Todos los estados"
            value={state}
            onChange={setState}
            queryKey={["stats-state"]}
            minChars={1}
            placeholder={GEO_SEARCH_HINTS.state}
            search={(term) => searchGeoItems(term, ["state"])}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="stats-days">Crecimiento de los últimos</Label>
          <select
            id="stats-days"
            className={SELECT_CLASS}
            value={days}
            onChange={(event) =>
              navigate({ search: (prev) => ({ ...prev, days: Number(event.target.value) }) })
            }
          >
            {[30, 90, 180, 365].map((value) => (
              <option key={value} value={value}>
                {value} días
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Card>
          <CardHeader>
            <CardTitle>
              <h2>
                Activos por {(GEO_LEVEL_PLURALS[level] ?? level).toLowerCase()}{" "}
                <span className="font-normal text-muted-foreground">({formatCount(total)})</span>
              </h2>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ProblemAlert error={geography.error} />
            <div className="max-h-[32rem] overflow-y-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">Pacificadores activos por zona y nivel</caption>
                <thead className="sticky top-0 bg-card text-xs text-muted-foreground">
                  <tr>
                    <th className="py-1 text-left font-medium">Zona</th>
                    {levels.map((l) => (
                      <th key={l.id} className="px-1 py-1 text-right font-medium">
                        {l.name.replace(/ de (la )?Paz/, "")}
                      </th>
                    ))}
                    <th className="py-1 text-right font-medium">Total</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {geography.data?.map((row) => (
                    <tr key={row.node_id}>
                      <td className="py-1.5">{row.label}</td>
                      {levels.map((l) => (
                        <td
                          key={l.id}
                          className="px-1 text-right tabular-nums text-muted-foreground"
                        >
                          {formatCount(row.by_level[l.code] ?? 0)}
                        </td>
                      ))}
                      <td className="text-right font-medium tabular-nums">
                        {formatCount(row.active)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {geography.data?.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  Sin pacificadores activos en esta selección.
                </p>
              ) : null}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>
              <h2>Inscripciones validadas por día</h2>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ProblemAlert error={growth.error} />
            <GrowthChart points={growth.data ?? []} from={from} days={days} />
          </CardContent>
        </Card>
      </div>
    </section>
  );
}

/** Bars per day (no chart library): fills missing days with zero. */
function GrowthChart({ points, from, days }: { points: GrowthPoint[]; from: Date; days: number }) {
  const byDay = new Map(points.map((p) => [p.day, p.enrollments]));
  const series = Array.from({ length: days }, (_, i) => {
    const day = isoDay(new Date(from.getTime() + i * 86_400_000));
    return { day, value: byDay.get(day) ?? 0 };
  });
  const max = Math.max(1, ...series.map((p) => p.value));
  const total = series.reduce((sum, p) => sum + p.value, 0);
  return (
    <figure className="space-y-2">
      <div className="flex h-48 items-end gap-px" aria-hidden>
        {series.map((point) => (
          <div
            key={point.day}
            title={`${formatDate(point.day)}: ${point.value}`}
            className="flex-1 rounded-t bg-primary/80"
            style={{ height: `${(point.value / max) * 100}%`, minHeight: point.value ? 2 : 0 }}
          />
        ))}
      </div>
      <figcaption className="flex justify-between text-xs text-muted-foreground">
        <span>{formatDate(series[0]?.day)}</span>
        <span>
          {total
            ? `${formatCount(total)} en ${days} días · máximo ${formatCount(max)} en un día`
            : "Sin inscripciones validadas en el periodo"}
        </span>
        <span>{formatDate(series.at(-1)?.day)}</span>
      </figcaption>
    </figure>
  );
}
