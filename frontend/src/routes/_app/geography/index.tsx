import { useQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { z } from "zod";
import { listGeoNodesOptions } from "@/client/@tanstack/react-query.gen";
import type { GeoNodeOut } from "@/client/types.gen";
import { type Column, DataTable } from "@/components/data/data-table";
import { useCursorPager } from "@/components/data/use-cursor-pager";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { SearchInput } from "@/components/search-input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { GeoName } from "@/features/candidacies/geo-name";
import { useDebounced } from "@/hooks/use-debounced";
import { GEO_LEVEL_LABELS } from "@/lib/labels";

export const LEVELS = [
  "electoral_region",
  "state",
  "municipality",
  "federal_district",
  "local_district",
  "section",
  "locality",
  "neighborhood",
] as const;
export type ExplorerLevel = (typeof LEVELS)[number];

const search = z.object({
  level: z.enum(LEVELS).catch("state"),
  state_id: z.string().optional(),
  municipality_id: z.string().optional(),
  federal_district_id: z.string().optional(),
  local_district_id: z.string().optional(),
  electoral_region_id: z.string().optional(),
});

export const Route = createFileRoute("/_app/geography/")({
  validateSearch: search,
  component: ExplorerPage,
});

const PARENT_FILTERS = [
  ["electoral_region_id", "electoral_region"],
  ["state_id", "state"],
  ["municipality_id", "municipality"],
  ["federal_district_id", "federal_district"],
  ["local_district_id", "local_district"],
] as const;

function ExplorerPage() {
  const filters = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const [term, setTerm] = useState("");
  const q = useDebounced(term.trim(), 300);
  const { level, ...parents } = filters;
  const { cursor, pager } = useCursorPager(JSON.stringify([filters, q]));
  const nodes = useQuery(
    listGeoNodesOptions({
      path: { level },
      query: { ...parents, q: q || undefined, cursor, limit: 50 },
    }),
  );
  const columns: Column<GeoNodeOut>[] = [
    {
      id: "key",
      header: "Clave INE",
      cell: ({ row }) => <code className="text-xs">{row.original.key}</code>,
    },
    { id: "name", header: "Nombre", cell: ({ row }) => row.original.name ?? "—" },
    ...(level !== "state" && level !== "electoral_region"
      ? [
          {
            id: "state",
            header: "Estado",
            cell: ({ row }: { row: { original: GeoNodeOut } }) => (
              <GeoName level="state" id={row.original.state_id} />
            ),
          } as Column<GeoNodeOut>,
        ]
      : []),
  ];
  const activeParents = PARENT_FILTERS.filter(([key]) => parents[key]);

  return (
    <section>
      <PageHeader
        title="Geografía electoral"
        description="Consulta de solo lectura del marco activo, limitada a tu alcance. Abre un registro para ver su mapa, ancestros y lo que contiene."
      />
      <Tabs
        value={level}
        onValueChange={(value) => navigate({ search: { level: value as ExplorerLevel } })}
      >
        <TabsList className="flex-wrap">
          {LEVELS.map((l) => (
            <TabsTrigger key={l} value={l}>
              {GEO_LEVEL_LABELS[l]}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      <div className="my-4 flex flex-wrap items-center gap-3">
        <SearchInput
          value={term}
          onChange={setTerm}
          label={`Buscar ${(GEO_LEVEL_LABELS[level] ?? "").toLowerCase()} por clave o nombre`}
        />
        {activeParents.map(([key, parentLevel]) => (
          <button
            key={key}
            type="button"
            className="rounded-full border px-3 py-1 text-xs hover:bg-muted"
            onClick={() => navigate({ search: (prev) => ({ ...prev, [key]: undefined }) })}
            aria-label={`Quitar filtro de ${GEO_LEVEL_LABELS[parentLevel]}`}
          >
            {GEO_LEVEL_LABELS[parentLevel]}: <GeoName level={parentLevel} id={parents[key]} /> ✕
          </button>
        ))}
      </div>
      <ProblemAlert error={nodes.error} />
      <DataTable
        caption={GEO_LEVEL_LABELS[level] ?? level}
        columns={columns}
        data={nodes.data?.items}
        isLoading={nodes.isPending}
        getRowId={(r) => r.id}
        pager={pager(nodes.data)}
        onActivate={(row) =>
          navigate({
            to: "/geography/$level/$nodeId",
            params: { level: row.level, nodeId: row.id },
          })
        }
      />
    </section>
  );
}
