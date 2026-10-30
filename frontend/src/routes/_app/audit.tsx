import { useQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { z } from "zod";
import {
  listAccessEntriesOptions,
  listAuditEntriesOptions,
} from "@/client/@tanstack/react-query.gen";
import type { AccessEntryOut, AuditEntryOut } from "@/client/types.gen";
import { type Column, DataTable } from "@/components/data/data-table";
import { useCursorPager } from "@/components/data/use-cursor-pager";
import { FormDialog } from "@/components/form-dialog";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatDateTime } from "@/lib/labels";

const search = z.object({
  view: z.enum(["writes", "reads"]).optional(),
  action: z.string().optional(),
  entity_table: z.string().optional(),
  entity_id: z.string().optional(),
  actor_user_id: z.string().optional(),
  request_id: z.string().optional(),
  occurred_from: z.string().optional(),
  occurred_to: z.string().optional(),
});

export const Route = createFileRoute("/_app/audit")({
  validateSearch: search,
  component: AuditPage,
});

const columns: Column<AuditEntryOut>[] = [
  { id: "when", header: "Fecha", cell: ({ row }) => formatDateTime(row.original.occurred_at) },
  {
    id: "action",
    header: "Acción",
    cell: ({ row }) => <code className="text-xs">{row.original.action}</code>,
  },
  {
    id: "entity",
    header: "Registro",
    cell: ({ row }) => (
      <span className="text-xs">
        {row.original.entity_table ?? "—"}
        {row.original.entity_id ? (
          <span className="block text-muted-foreground">{row.original.entity_id}</span>
        ) : null}
      </span>
    ),
  },
  {
    id: "actor",
    header: "Usuario",
    cell: ({ row }) => (
      <code className="text-xs">{row.original.actor_user_id?.slice(0, 8) ?? "sistema"}</code>
    ),
  },
  { id: "ip", header: "IP", cell: ({ row }) => row.original.actor_ip ?? "—" },
];

const ACCESS_ACTIONS: Record<string, string> = { read: "Consulta", export: "Exportación" };

const accessColumns: Column<AccessEntryOut>[] = [
  { id: "when", header: "Fecha", cell: ({ row }) => formatDateTime(row.original.occurred_at) },
  {
    id: "action",
    header: "Lectura",
    cell: ({ row }) => ACCESS_ACTIONS[row.original.action] ?? row.original.action,
  },
  {
    id: "entity",
    header: "Registro",
    cell: ({ row }) => (
      <span className="text-xs">
        {row.original.entity_table}
        {row.original.entity_id ? (
          <span className="block text-muted-foreground">{row.original.entity_id}</span>
        ) : null}
      </span>
    ),
  },
  {
    id: "details",
    header: "Detalle",
    cell: ({ row }) => {
      const details = row.original.details ?? {};
      return (
        <span className="text-xs">
          {details.unmasked === true
            ? "Datos completos"
            : details.unmasked === false
              ? "Enmascarado"
              : ""}
          {typeof details.rows === "number" ? ` · ${details.rows} filas` : ""}
        </span>
      );
    },
  },
  {
    id: "actor",
    header: "Usuario",
    cell: ({ row }) => (
      <code className="text-xs">{row.original.actor_user_id?.slice(0, 8) ?? "—"}</code>
    ),
  },
  { id: "ip", header: "IP", cell: ({ row }) => row.original.actor_ip ?? "—" },
];

const FILTERS: [keyof z.infer<typeof search>, string, string?][] = [
  ["action", "Acción"],
  ["entity_table", "Tabla", "people.persons"],
  ["entity_id", "Id del registro"],
  ["actor_user_id", "Id del usuario"],
  ["occurred_from", "Desde", "date"],
  ["occurred_to", "Hasta", "date"],
];

/** Immutable audit log (hash chain, D-36): who, what, when, from where, before and after. */
function AuditPage() {
  const filters = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const [selected, setSelected] = useState<AuditEntryOut | null>(null);
  const { view: viewParam, ...rest } = filters;
  const view = viewParam ?? "writes";
  const { cursor, pager } = useCursorPager(JSON.stringify(filters));
  const range = {
    occurred_from: rest.occurred_from ? `${rest.occurred_from}T00:00:00Z` : undefined,
    occurred_to: rest.occurred_to ? `${rest.occurred_to}T23:59:59Z` : undefined,
  };
  const entries = useQuery({
    ...listAuditEntriesOptions({ query: { ...rest, ...range, cursor, limit: 50 } }),
    enabled: view === "writes",
  });
  const { request_id: _request, ...accessFilters } = rest;
  const reads = useQuery({
    ...listAccessEntriesOptions({ query: { ...accessFilters, ...range, cursor, limit: 50 } }),
    enabled: view === "reads",
  });
  return (
    <section>
      <PageHeader
        title="Bitácora de auditoría"
        description="Toda escritura del sistema queda registrada; la bitácora no se puede modificar. Las consultas de datos sensibles (detalles y exportaciones) se registran aparte."
      />
      <Tabs
        value={view}
        onValueChange={(value) =>
          navigate({ search: (p) => ({ ...p, view: value as "writes" | "reads" }) })
        }
        className="mb-4"
      >
        <TabsList>
          <TabsTrigger value="writes">Escrituras</TabsTrigger>
          <TabsTrigger value="reads">Lecturas sensibles</TabsTrigger>
        </TabsList>
      </Tabs>
      <form
        className="mb-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-6"
        onSubmit={(e) => e.preventDefault()}
      >
        {FILTERS.filter(([key]) => view === "writes" || key !== "request_id").map(
          ([key, label, hint]) => (
            <div key={key} className="grid gap-1">
              <Label htmlFor={`audit-${key}`} className="text-xs">
                {label}
              </Label>
              <Input
                id={`audit-${key}`}
                type={hint === "date" ? "date" : "text"}
                placeholder={hint !== "date" ? hint : undefined}
                defaultValue={filters[key] ?? ""}
                onBlur={(e) =>
                  navigate({ search: (p) => ({ ...p, [key]: e.target.value.trim() || undefined }) })
                }
                onKeyDown={(e) => {
                  if (e.key === "Enter") e.currentTarget.blur();
                }}
              />
            </div>
          ),
        )}
      </form>
      {view === "writes" ? (
        <>
          <ProblemAlert error={entries.error} />
          <DataTable
            caption="Entradas de la bitácora"
            columns={columns}
            data={entries.data?.items}
            isLoading={entries.isPending}
            getRowId={(r) => r.id}
            pager={pager(entries.data)}
            onActivate={setSelected}
          />
        </>
      ) : (
        <>
          <ProblemAlert error={reads.error} />
          <DataTable
            caption="Lecturas sensibles"
            columns={accessColumns}
            data={reads.data?.items}
            isLoading={reads.isPending}
            getRowId={(r) => r.id}
            pager={pager(reads.data)}
            empty="Sin lecturas registradas con estos filtros."
          />
        </>
      )}
      {selected ? (
        <FormDialog
          open
          onOpenChange={(o) => !o && setSelected(null)}
          title={`Entrada #${selected.chain_seq}`}
          wide
        >
          <div className="grid gap-3 text-sm">
            <p>
              {formatDateTime(selected.occurred_at)} · <code>{selected.action}</code> · IP{" "}
              {selected.actor_ip ?? "—"} · solicitud{" "}
              <code className="text-xs">{selected.request_id ?? "—"}</code>
            </p>
            <div className="grid gap-3 md:grid-cols-2">
              {(["before", "after"] as const).map((key) => (
                <div key={key}>
                  <p className="text-xs font-medium text-muted-foreground">
                    {key === "before" ? "Antes" : "Después"}
                  </p>
                  <pre className="max-h-80 overflow-auto rounded bg-muted p-2 text-xs">
                    {JSON.stringify(selected[key], null, 2) ?? "—"}
                  </pre>
                </div>
              ))}
            </div>
          </div>
        </FormDialog>
      ) : null}
    </section>
  );
}
