import { useQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { z } from "zod";
import { listNominationsOptions } from "@/client/@tanstack/react-query.gen";
import type { NominationStatus, NominationSummary } from "@/client/types.gen";
import { type Column, DataTable } from "@/components/data/data-table";
import { useCursorPager } from "@/components/data/use-cursor-pager";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { GeoName } from "@/features/candidacies/geo-name";
import { useCatalogs } from "@/features/candidacies/use-catalogs";
import { useHotkey } from "@/hooks/use-hotkey";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";
import { formatDateTime, NOMINATION_STATUS } from "@/lib/labels";

const search = z.object({
  process_id: z.string().optional(),
  office_type_id: z.string().optional(),
  status: z.enum(["draft", "submitted", "approved", "cancelled"]).optional(),
  sort: z.string().optional(),
});

export const Route = createFileRoute("/_app/nominations/")({
  validateSearch: search,
  component: NominationsPage,
});

const selectClass = "h-8 rounded-lg border border-input bg-transparent px-2 text-sm";

function NominationsPage() {
  const filters = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const can = useCan();
  const { offices, processes, officeById, partyById, processById } = useCatalogs();
  const { cursor, pager } = useCursorPager(JSON.stringify(filters));
  const nominations = useQuery(
    listNominationsOptions({
      query: {
        ...filters,
        status: filters.status as NominationStatus | undefined,
        cursor,
        limit: 50,
      },
    }),
  );
  const write = can(Perm.NOMINATION_WRITE);
  const newNomination = () =>
    navigate({ to: "/nominations/new", search: { process_id: filters.process_id } });
  useHotkey("n", newNomination, write);

  const columns: Column<NominationSummary>[] = [
    {
      id: "office",
      header: "Cargo",
      cell: ({ row }) => (
        <span className="font-medium">
          {officeById.get(row.original.office_type_id)?.name ?? row.original.office_code}
        </span>
      ),
    },
    {
      id: "node",
      header: "Geografía",
      cell: ({ row }) => (
        <GeoName level={row.original.geographic_level} id={row.original.node_id} withLevel />
      ),
    },
    {
      id: "nominator",
      header: "Postula",
      cell: ({ row }) =>
        row.original.party_id
          ? (partyById.get(row.original.party_id)?.acronym ?? "Partido")
          : "Coalición",
    },
    {
      id: "process",
      header: "Proceso",
      cell: ({ row }) => processById.get(row.original.process_id)?.name ?? "—",
    },
    {
      id: "status",
      header: "Estatus",
      sortKey: "status",
      cell: ({ row }) => (
        <Badge variant="secondary">{NOMINATION_STATUS[row.original.status]}</Badge>
      ),
    },
    {
      id: "created",
      header: "Creada",
      sortKey: "created_at",
      cell: ({ row }) => formatDateTime(row.original.created_at),
    },
  ];

  function setFilter(key: keyof z.infer<typeof search>, value: string) {
    navigate({ search: (prev) => ({ ...prev, [key]: value || undefined }) });
  }

  return (
    <section>
      <PageHeader
        title="Postulaciones"
        description="Planillas, listas y fórmulas por cargo y geografía. Solo ves las que tocan tu alcance geográfico."
        actions={
          write ? (
            <Button onClick={newNomination}>
              <Plus aria-hidden /> Nueva postulación
            </Button>
          ) : null
        }
      />
      <div className="mb-4 flex flex-wrap gap-2">
        <select
          aria-label="Proceso"
          className={selectClass}
          value={filters.process_id ?? ""}
          onChange={(e) => setFilter("process_id", e.target.value)}
        >
          <option value="">Todos los procesos</option>
          {processes.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <select
          aria-label="Cargo"
          className={selectClass}
          value={filters.office_type_id ?? ""}
          onChange={(e) => setFilter("office_type_id", e.target.value)}
        >
          <option value="">Todos los cargos</option>
          {offices
            .filter((o) => o.nomination_kind !== "member")
            .map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
        </select>
        <select
          aria-label="Estatus"
          className={selectClass}
          value={filters.status ?? ""}
          onChange={(e) => setFilter("status", e.target.value)}
        >
          <option value="">Todos los estatus</option>
          {Object.entries(NOMINATION_STATUS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>
      <ProblemAlert error={nominations.error} />
      <DataTable
        caption="Postulaciones"
        columns={columns}
        data={nominations.data?.items}
        isLoading={nominations.isPending}
        getRowId={(r) => r.id}
        pager={pager(nominations.data)}
        sort={filters.sort ?? "-created_at"}
        onSortChange={(sort) => setFilter("sort", sort)}
        onActivate={(row) =>
          navigate({ to: "/nominations/$nominationId", params: { nominationId: row.id } })
        }
      />
    </section>
  );
}
