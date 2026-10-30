import { useQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { useState } from "react";
import { z } from "zod";
import { searchMembersOptions } from "@/client/@tanstack/react-query.gen";
import type { MemberSummary } from "@/client/types.gen";
import { type Column, DataTable } from "@/components/data/data-table";
import { useCursorPager } from "@/components/data/use-cursor-pager";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { SearchInput } from "@/components/search-input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { MEMBER_STATUS, SELECT_CLASS } from "@/features/peace-movement/labels";
import { LevelSelect, MemberStatusBadge, useLevels } from "@/features/peace-movement/shared";
import { useDebounced } from "@/hooks/use-debounced";
import { useHotkey } from "@/hooks/use-hotkey";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";
import { formatDate } from "@/lib/labels";

const STATUSES = ["active", "pending_validation", "left", "rejected", "withdrawn"] as const;
type Status = (typeof STATUSES)[number];

export const Route = createFileRoute("/_app/peace-movement/members/")({
  validateSearch: z.object({
    q: z.string().optional(),
    status: z.enum(STATUSES).optional(),
    level: z.string().optional(),
    sort: z.string().optional(),
  }),
  component: MembersPage,
});

function MembersPage() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const can = useCan();
  const { levels, byId } = useLevels();
  const [term, setTerm] = useState(search.q ?? "");
  const q = useDebounced(term.trim(), 300);
  const filters = {
    ...(q.length >= 2 ? { q } : {}),
    ...(search.status ? { status: search.status } : {}),
    ...(search.level ? { level_id: search.level } : {}),
  };
  const { cursor, pager } = useCursorPager(JSON.stringify([filters, search.sort]));
  const members = useQuery(
    searchMembersOptions({ query: { ...filters, sort: search.sort, cursor, limit: 50 } }),
  );
  const write = can(Perm.PEACE_MEMBER_WRITE);
  useHotkey("n", () => navigate({ to: "/peace-movement/members/new" }), write);

  const columns: Column<MemberSummary>[] = [
    {
      id: "name",
      header: "Nombre",
      cell: ({ row }) => <span className="font-medium">{row.original.person.full_name}</span>,
    },
    {
      id: "level",
      header: "Nivel",
      cell: ({ row }) => byId.get(row.original.level_id)?.name ?? "—",
    },
    {
      id: "status",
      header: "Estatus",
      cell: ({ row }) => <MemberStatusBadge status={row.original.status} />,
    },
    {
      id: "depth",
      header: "Nivel en la red",
      sortKey: "depth",
      cell: ({ row }) => (
        <span className="tabular-nums">
          {row.original.depth === 0 ? "Raíz" : row.original.depth}
        </span>
      ),
    },
    {
      id: "enrolled",
      header: "Inscripción",
      sortKey: "enrolled_on",
      cell: ({ row }) => formatDate(row.original.enrolled_on),
    },
  ];

  return (
    <section>
      <PageHeader
        title="Pacificadores"
        description="Integrantes del Movimiento de Paz dentro de tu alcance (geográfico o por rama)."
        actions={
          write ? (
            <Button onClick={() => navigate({ to: "/peace-movement/members/new" })}>
              <Plus aria-hidden /> Inscribir
            </Button>
          ) : null
        }
      />
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="min-w-64 flex-1">
          <SearchInput value={term} onChange={setTerm} label="Buscar por nombre" />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="member-status">Estatus</Label>
          <select
            id="member-status"
            className={SELECT_CLASS}
            value={search.status ?? ""}
            onChange={(event) =>
              navigate({
                search: (prev) => ({
                  ...prev,
                  status: (event.target.value || undefined) as Status | undefined,
                }),
              })
            }
          >
            <option value="">Todos</option>
            {STATUSES.map((status) => (
              <option key={status} value={status}>
                {MEMBER_STATUS[status]}
              </option>
            ))}
          </select>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="member-level">Nivel de participación</Label>
          <LevelSelect
            id="member-level"
            levels={levels}
            allowEmpty
            value={search.level ?? ""}
            onChange={(level) =>
              navigate({ search: (prev) => ({ ...prev, level: level || undefined }) })
            }
          />
        </div>
      </div>
      <ProblemAlert error={members.error} />
      <DataTable
        caption="Pacificadores"
        columns={columns}
        data={members.data?.items}
        isLoading={members.isPending}
        getRowId={(row) => row.id}
        pager={pager(members.data)}
        sort={search.sort ?? "-created_at"}
        onSortChange={(sort) => navigate({ search: (prev) => ({ ...prev, sort }) })}
        onActivate={(row) =>
          navigate({ to: "/peace-movement/members/$memberId", params: { memberId: row.id } })
        }
        empty="No hay pacificadores con estos filtros."
      />
    </section>
  );
}
