import { useQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { listImportRunsOptions } from "@/client/@tanstack/react-query.gen";
import type { ImportRunOut } from "@/client/types.gen";
import { type Column, DataTable } from "@/components/data/data-table";
import { useCursorPager } from "@/components/data/use-cursor-pager";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Badge } from "@/components/ui/badge";
import { formatDateTime, RUN_STATUS } from "@/lib/labels";

export const Route = createFileRoute("/_app/geography/imports/")({ component: ImportsPage });

const columns: Column<ImportRunOut>[] = [
  { id: "started", header: "Inicio", cell: ({ row }) => formatDateTime(row.original.started_at) },
  {
    id: "state",
    header: "Estado (INE)",
    cell: ({ row }) => row.original.state_code ?? "Catálogos",
  },
  {
    id: "status",
    header: "Resultado",
    cell: ({ row }) => (
      <span className="flex gap-1">
        <Badge variant={row.original.status === "failed" ? "destructive" : "secondary"}>
          {RUN_STATUS[row.original.status] ?? row.original.status}
        </Badge>
        {row.original.dry_run ? <Badge variant="outline">Simulación</Badge> : null}
      </span>
    ),
  },
  { id: "errors", header: "Errores", cell: ({ row }) => row.original.error_count },
  { id: "warnings", header: "Advertencias", cell: ({ row }) => row.original.warning_count },
  { id: "by", header: "Lanzada por", cell: ({ row }) => row.original.triggered_by ?? "—" },
];

function ImportsPage() {
  const navigate = useNavigate();
  const { cursor, pager } = useCursorPager("runs");
  const runs = useQuery(listImportRunsOptions({ query: { cursor, limit: 50 } }));
  return (
    <section>
      <PageHeader
        title="Importaciones del INE"
        description="Corridas de `paz geo import` (se lanzan por línea de comandos, D-42) con su reporte por registro."
      />
      <ProblemAlert error={runs.error} />
      <DataTable
        caption="Corridas de importación"
        columns={columns}
        data={runs.data?.items}
        isLoading={runs.isPending}
        getRowId={(r) => r.id}
        pager={pager(runs.data)}
        onActivate={(row) =>
          navigate({ to: "/geography/imports/$runId", params: { runId: row.id } })
        }
      />
    </section>
  );
}
