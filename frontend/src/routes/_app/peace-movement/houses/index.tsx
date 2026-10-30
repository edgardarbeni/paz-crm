import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Map as MapIcon, Plus } from "lucide-react";
import { z } from "zod";
import { searchPeaceHousesOptions } from "@/client/@tanstack/react-query.gen";
import type { HouseSummary } from "@/client/types.gen";
import { type Column, DataTable } from "@/components/data/data-table";
import { useCursorPager } from "@/components/data/use-cursor-pager";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { HOUSE_STATUS, SELECT_CLASS } from "@/features/peace-movement/labels";
import { HouseStatusBadge } from "@/features/peace-movement/shared";
import { useHotkey } from "@/hooks/use-hotkey";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";
import { formatDate } from "@/lib/labels";

const STATUSES = ["open", "consolidated", "closed"] as const;
const FLAGS = {
  credit_pending: "Crédito pendiente",
  needs_reassignment: "Sin anfitrión o contacto",
  publishable: "Ubicación publicable",
} as const;
type Flag = keyof typeof FLAGS;

export const Route = createFileRoute("/_app/peace-movement/houses/")({
  validateSearch: z.object({
    status: z.enum(STATUSES).optional(),
    flag: z.enum(["credit_pending", "needs_reassignment", "publishable"]).optional(),
    sort: z.string().optional(),
  }),
  component: HousesPage,
});

const columns: Column<HouseSummary>[] = [
  {
    id: "name",
    header: "Casa",
    sortKey: "name",
    cell: ({ row }) => <span className="font-medium">{row.original.name}</span>,
  },
  {
    id: "status",
    header: "Estatus",
    cell: ({ row }) => <HouseStatusBadge status={row.original.status} />,
  },
  {
    id: "members",
    header: "Integrantes",
    cell: ({ row }) => <span className="tabular-nums">{row.original.member_count}</span>,
  },
  {
    id: "flags",
    header: "Atención",
    cell: ({ row }) => (
      <div className="flex flex-wrap gap-1">
        {row.original.credit_pending ? <Badge variant="secondary">Crédito pendiente</Badge> : null}
        {row.original.needs_reassignment ? (
          <Badge variant="destructive">Sin anfitrión o contacto</Badge>
        ) : null}
        {row.original.publishable ? <Badge variant="outline">Publicable</Badge> : null}
      </div>
    ),
  },
  {
    id: "opened",
    header: "Apertura",
    sortKey: "opened_on",
    cell: ({ row }) => formatDate(row.original.opened_on),
  },
];

function HousesPage() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const can = useCan();
  const filters = {
    ...(search.status ? { status: search.status } : {}),
    ...(search.flag ? { [search.flag]: true } : {}),
  };
  const { cursor, pager } = useCursorPager(JSON.stringify([filters, search.sort]));
  const houses = useQuery(
    searchPeaceHousesOptions({ query: { ...filters, sort: search.sort, cursor, limit: 50 } }),
  );
  const write = can(Perm.PEACE_HOUSE_WRITE);
  useHotkey("n", () => navigate({ to: "/peace-movement/houses/new" }), write);

  return (
    <section>
      <PageHeader
        title="Casas de Paz"
        description="Puntos de encuentro georreferenciados. Una casa se consolida al llegar a la meta de integrantes de su estado."
        actions={
          <>
            <Button asChild variant="outline">
              <Link to="/peace-movement/houses/map">
                <MapIcon aria-hidden /> Ver mapa
              </Link>
            </Button>
            {write ? (
              <Button onClick={() => navigate({ to: "/peace-movement/houses/new" })}>
                <Plus aria-hidden /> Abrir casa
              </Button>
            ) : null}
          </>
        }
      />
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="grid gap-1.5">
          <Label htmlFor="house-status">Estatus</Label>
          <select
            id="house-status"
            className={SELECT_CLASS}
            value={search.status ?? ""}
            onChange={(event) =>
              navigate({
                search: (prev) => ({
                  ...prev,
                  status: (event.target.value || undefined) as (typeof STATUSES)[number],
                }),
              })
            }
          >
            <option value="">Todas</option>
            {STATUSES.map((status) => (
              <option key={status} value={status}>
                {HOUSE_STATUS[status]}
              </option>
            ))}
          </select>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="house-flag">Requieren atención</Label>
          <select
            id="house-flag"
            className={SELECT_CLASS}
            value={search.flag ?? ""}
            onChange={(event) =>
              navigate({
                search: (prev) => ({ ...prev, flag: (event.target.value || undefined) as Flag }),
              })
            }
          >
            <option value="">Sin filtro</option>
            {Object.entries(FLAGS).map(([flag, label]) => (
              <option key={flag} value={flag}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <ProblemAlert error={houses.error} />
      <DataTable
        caption="Casas de Paz"
        columns={columns}
        data={houses.data?.items}
        isLoading={houses.isPending}
        getRowId={(row) => row.id}
        pager={pager(houses.data)}
        sort={search.sort ?? "-opened_on"}
        onSortChange={(sort) => navigate({ search: (prev) => ({ ...prev, sort }) })}
        onActivate={(row) =>
          navigate({ to: "/peace-movement/houses/$houseId", params: { houseId: row.id } })
        }
        empty="No hay casas con estos filtros."
      />
    </section>
  );
}
