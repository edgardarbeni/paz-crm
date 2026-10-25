import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { getImportRunOptions, listImportIssuesOptions } from "@/client/@tanstack/react-query.gen";
import type { ImportIssueOut } from "@/client/types.gen";
import { type Column, DataTable } from "@/components/data/data-table";
import { useCursorPager } from "@/components/data/use-cursor-pager";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Card, CardContent } from "@/components/ui/card";
import { formatDateTime, RUN_STATUS } from "@/lib/labels";

export const Route = createFileRoute("/_app/geography/imports/$runId")({ component: RunPage });

const columns: Column<ImportIssueOut>[] = [
  {
    id: "severity",
    header: "Tipo",
    cell: ({ row }) => (row.original.severity === "error" ? "Error" : "Advertencia"),
  },
  { id: "layer", header: "Capa", cell: ({ row }) => row.original.layer },
  {
    id: "code",
    header: "Código",
    cell: ({ row }) => <code className="text-xs">{row.original.code}</code>,
  },
  {
    id: "key",
    header: "Registro",
    cell: ({ row }) => (
      <code className="text-xs">
        {JSON.stringify(row.original.natural_key ?? row.original.source_fid)}
      </code>
    ),
  },
  { id: "message", header: "Detalle", cell: ({ row }) => row.original.message },
];

function RunPage() {
  const { runId } = Route.useParams();
  const [severity, setSeverity] = useState("");
  const run = useQuery(getImportRunOptions({ path: { run_id: runId } }));
  const { cursor, pager } = useCursorPager(severity);
  const issues = useQuery(
    listImportIssuesOptions({
      path: { run_id: runId },
      query: { severity: severity || undefined, cursor, limit: 100 },
    }),
  );
  const r = run.data;
  return (
    <section>
      <PageHeader
        title="Corrida de importación"
        description={
          r ? `${formatDateTime(r.started_at)} · ${RUN_STATUS[r.status] ?? r.status}` : undefined
        }
      />
      <ProblemAlert error={run.error ?? issues.error} />
      {r ? (
        <Card className="mb-6">
          <CardContent className="grid gap-4 text-sm md:grid-cols-2">
            <div>
              <p className="text-xs text-muted-foreground">Origen</p>
              <p className="break-all">{r.source_uri}</p>
              {r.file_sha256 ? (
                <p className="break-all font-mono text-xs text-muted-foreground">
                  SHA-256 {r.file_sha256}
                </p>
              ) : null}
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Capas</p>
              <p>Cargadas: {r.layers_loaded.join(", ") || "—"}</p>
              {r.layers_missing.length ? <p>Faltantes: {r.layers_missing.join(", ")}</p> : null}
            </div>
            <div className="md:col-span-2">
              <p className="text-xs text-muted-foreground">Conteos</p>
              <pre className="overflow-x-auto rounded bg-muted p-2 text-xs">
                {JSON.stringify(r.counts, null, 2)}
              </pre>
            </div>
            {r.message ? <p className="md:col-span-2">{r.message}</p> : null}
          </CardContent>
        </Card>
      ) : null}
      <div className="mb-3 flex items-center gap-2">
        <h2 className="text-base font-semibold">Incidencias</h2>
        <select
          aria-label="Tipo de incidencia"
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
          className="h-8 rounded-lg border border-input bg-transparent px-2 text-sm"
        >
          <option value="">Todas</option>
          <option value="error">Errores</option>
          <option value="warning">Advertencias</option>
        </select>
      </div>
      <DataTable
        caption="Incidencias de la corrida"
        columns={columns}
        data={issues.data?.items}
        isLoading={issues.isPending}
        getRowId={(row) => String(row.id)}
        pager={pager(issues.data)}
        empty="Sin incidencias."
      />
    </section>
  );
}
