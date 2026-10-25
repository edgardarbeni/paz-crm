import { useQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { useState } from "react";
import { z } from "zod";
import { searchPeopleOptions } from "@/client/@tanstack/react-query.gen";
import type { PersonSummary } from "@/client/types.gen";
import { type Column, DataTable } from "@/components/data/data-table";
import { useCursorPager } from "@/components/data/use-cursor-pager";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { SearchInput } from "@/components/search-input";
import { Button } from "@/components/ui/button";
import { useDebounced } from "@/hooks/use-debounced";
import { useHotkey } from "@/hooks/use-hotkey";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";
import { formatDate, SEX_LABELS } from "@/lib/labels";

export const Route = createFileRoute("/_app/people/")({
  validateSearch: z.object({ q: z.string().optional(), sort: z.string().optional() }),
  component: PeoplePage,
});

const columns: Column<PersonSummary>[] = [
  {
    id: "name",
    header: "Nombre",
    sortKey: "paternal_surname",
    cell: ({ row }) => <span className="font-medium">{row.original.full_name}</span>,
  },
  {
    id: "curp",
    header: "CURP",
    cell: ({ row }) => <code className="text-xs">{row.original.curp ?? "—"}</code>,
  },
  {
    id: "sex",
    header: "Sexo",
    cell: ({ row }) => (row.original.sex ? SEX_LABELS[row.original.sex] : "—"),
  },
  { id: "birth", header: "Nacimiento", cell: ({ row }) => formatDate(row.original.birth_date) },
];

const CURP_LIKE = /^[A-Z]{4}\d{6}[HMX][A-Z]{5}[0-9A-Z]\d$/i;

function PeoplePage() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const can = useCan();
  const [term, setTerm] = useState(search.q ?? "");
  const q = useDebounced(term.trim(), 300);
  const query = CURP_LIKE.test(q)
    ? { curp: q.toUpperCase() }
    : /^[\d\s()+-]{10,}$/.test(q)
      ? { phone: q.replace(/\D/g, "") }
      : q.length >= 2
        ? { q }
        : {};
  const { cursor, pager } = useCursorPager(JSON.stringify([query, search.sort]));
  const people = useQuery(
    searchPeopleOptions({ query: { ...query, sort: search.sort, cursor, limit: 50 } }),
  );
  const write = can(Perm.PERSON_WRITE);
  useHotkey("n", () => navigate({ to: "/people/new" }), write);

  return (
    <section>
      <PageHeader
        title="Personas"
        description="Base única de personas (candidaturas hoy, padrón después). Busca por nombre, CURP o teléfono."
        actions={
          write ? (
            <Button onClick={() => navigate({ to: "/people/new" })}>
              <Plus aria-hidden /> Nueva persona
            </Button>
          ) : null
        }
      />
      <div className="mb-4">
        <SearchInput value={term} onChange={setTerm} label="Buscar por nombre, CURP o teléfono" />
      </div>
      <ProblemAlert error={people.error} />
      <DataTable
        caption="Personas"
        columns={columns}
        data={people.data?.items}
        isLoading={people.isPending}
        getRowId={(r) => r.id}
        pager={pager(people.data)}
        sort={search.sort ?? "paternal_surname"}
        onSortChange={(sort) => navigate({ search: (prev) => ({ ...prev, sort }) })}
        onActivate={(row) => navigate({ to: "/people/$personId", params: { personId: row.id } })}
      />
    </section>
  );
}
