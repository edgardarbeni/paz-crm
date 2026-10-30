import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { FileUp } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import {
  listMemberImportErrorsOptions,
  listMemberImportsOptions,
  queueMemberImportMutation,
} from "@/client/@tanstack/react-query.gen";
import type { MemberImportRunOut } from "@/client/types.gen";
import { type Column, DataTable } from "@/components/data/data-table";
import { useCursorPager } from "@/components/data/use-cursor-pager";
import { FormDialog } from "@/components/form-dialog";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatCount, IMPORT_STATUS } from "@/features/peace-movement/labels";
import { LevelSelect, useLevels } from "@/features/peace-movement/shared";
import { formatDateTime } from "@/lib/labels";

export const Route = createFileRoute("/_app/peace-movement/imports")({
  component: ImportsPage,
});

const COLUMNS_HELP = [
  ["nombre", "obligatoria"],
  ["apellido_paterno", "obligatoria"],
  ["apellido_materno", ""],
  ["curp", "obligatoria"],
  ["celular · correo", ""],
  ["calle · numero_exterior · codigo_postal", ""],
  ["entidad · seccion", "obligatorias (de la credencial)"],
  ["nivel", "código o nombre; si falta, el nivel por defecto"],
  ["codigo_reclutador o curp_reclutador", "puede ser otra fila del archivo"],
  ["origen · detalle_origen", "structure, event o campaign si no hay reclutador"],
] as const;

function ImportsPage() {
  const queryClient = useQueryClient();
  const { levels } = useLevels();
  const file = useRef<HTMLInputElement>(null);
  const [picked, setPicked] = useState<File | null>(null);
  const [dryRun, setDryRun] = useState(true);
  const [evidence, setEvidence] = useState("");
  const [level, setLevel] = useState("");
  const { cursor, pager } = useCursorPager("imports");
  const runs = useQuery({
    ...listMemberImportsOptions({ query: { cursor, limit: 20 } }),
    // Runs are processed by the scheduler every minute: refresh while any is pending.
    refetchInterval: (query) =>
      query.state.data?.items.some((r) => r.status === "queued" || r.status === "running")
        ? 10_000
        : false,
  });
  const queue = useMutation({
    ...queueMemberImportMutation(),
    onSuccess: (run) => {
      toast.success(
        run.dry_run
          ? "Archivo en cola para validar. El resultado aparece en un par de minutos."
          : "Archivo en cola para importar.",
      );
      setPicked(null);
      if (file.current) file.current.value = "";
      queryClient.invalidateQueries({ queryKey: [{ _id: "listMemberImports" }] });
    },
  });

  const columns: Column<MemberImportRunOut>[] = [
    { id: "file", header: "Archivo", cell: ({ row }) => row.original.filename },
    {
      id: "mode",
      header: "Modo",
      cell: ({ row }) =>
        row.original.dry_run ? (
          <Badge variant="outline">Validación</Badge>
        ) : (
          <Badge>Importación</Badge>
        ),
    },
    {
      id: "status",
      header: "Estatus",
      cell: ({ row }) => (
        <span title={row.original.failure ?? undefined}>
          {IMPORT_STATUS[row.original.status] ?? row.original.status}
        </span>
      ),
    },
    {
      id: "rows",
      header: "Filas",
      cell: ({ row }) =>
        row.original.status === "done" ? (
          <span className="tabular-nums">
            {formatCount(row.original.accepted_rows)} aceptadas ·{" "}
            <span className={row.original.error_rows ? "text-destructive" : undefined}>
              {formatCount(row.original.error_rows)} con error
            </span>
          </span>
        ) : (
          "—"
        ),
    },
    {
      id: "created",
      header: "Subida",
      cell: ({ row }) => formatDateTime(row.original.created_at),
    },
    {
      id: "errors",
      header: "",
      cell: ({ row }) => (row.original.error_rows ? <ErrorsDialog run={row.original} /> : null),
    },
  ];

  return (
    <section className="max-w-6xl space-y-6">
      <PageHeader
        title="Importar pacificadores"
        description="Sube un CSV o Excel. Valídalo primero: la validación revisa cada fila sin escribir nada. Lo importado entra activo."
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <Card>
          <CardHeader>
            <CardTitle>
              <h2>Subir archivo</h2>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className="grid gap-4"
              onSubmit={(event) => {
                event.preventDefault();
                if (!picked) return;
                queue.mutate({
                  body: {
                    file: picked,
                    evidence_uri: evidence.trim(),
                    dry_run: dryRun,
                    ...(level ? { default_level_id: level } : {}),
                  },
                });
              }}
            >
              <ProblemAlert error={queue.error} />
              <div className="grid gap-1.5">
                <Label htmlFor="import-file">Archivo (.csv en UTF-8 o .xlsx, hasta 20 MB)</Label>
                <Input
                  id="import-file"
                  ref={file}
                  type="file"
                  accept=".csv,.xlsx"
                  onChange={(event) => setPicked(event.target.files?.[0] ?? null)}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="import-evidence">Evidencia de los consentimientos</Label>
                <Input
                  id="import-evidence"
                  value={evidence}
                  placeholder="Dónde están los formatos firmados del aviso del MP"
                  onChange={(event) => setEvidence(event.target.value)}
                  required
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="import-level">Nivel por defecto (filas sin «nivel»)</Label>
                <LevelSelect
                  id="import-level"
                  levels={levels}
                  allowEmpty
                  emptyLabel="Ninguno: la fila sin nivel es un error"
                  value={level}
                  onChange={setLevel}
                />
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="import-dry"
                  checked={dryRun}
                  onCheckedChange={(checked) => setDryRun(checked === true)}
                />
                <Label htmlFor="import-dry">Solo validar (no escribe nada)</Label>
              </div>
              <Button
                type="submit"
                className="justify-self-start"
                disabled={!picked || evidence.trim().length < 3 || queue.isPending}
              >
                <FileUp aria-hidden /> {dryRun ? "Validar archivo" : "Importar"}
              </Button>
            </form>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>
              <h2>Columnas</h2>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1.5 text-sm">
              {COLUMNS_HELP.map(([name, note]) => (
                <li key={name}>
                  <code className="text-xs">{name}</code>
                  {note ? <span className="text-muted-foreground"> — {note}</span> : null}
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-muted-foreground">
              Los encabezados no distinguen acentos ni mayúsculas. Hasta 100,000 filas.
            </p>
          </CardContent>
        </Card>
      </div>
      <ProblemAlert error={runs.error} />
      <DataTable
        caption="Importaciones"
        columns={columns}
        data={runs.data?.items}
        isLoading={runs.isPending}
        getRowId={(row) => row.id}
        pager={pager(runs.data)}
        empty="Aún no hay importaciones."
      />
    </section>
  );
}

function ErrorsDialog({ run }: { run: MemberImportRunOut }) {
  const [open, setOpen] = useState(false);
  const errors = useQuery({
    ...listMemberImportErrorsOptions({ path: { run_id: run.id }, query: { limit: 200 } }),
    enabled: open,
  });
  return (
    <FormDialog
      trigger={
        <Button size="sm" variant="ghost">
          Ver errores
        </Button>
      }
      title={`Errores de ${run.filename}`}
      description="Fila 1 = encabezados. Corrige el archivo y vuelve a subirlo."
      open={open}
      onOpenChange={setOpen}
      wide
    >
      <ProblemAlert error={errors.error} />
      <div className="max-h-96 overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-muted-foreground">
            <tr>
              <th className="py-1 text-left font-medium">Fila</th>
              <th className="py-1 text-left font-medium">Problema</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {errors.data?.items.map((error) => (
              <tr key={`${error.row_number}-${error.code}`}>
                <td className="py-1.5 pr-3 align-top tabular-nums">{error.row_number}</td>
                <td className="py-1.5">{error.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {errors.data?.has_more ? (
          <p className="pt-2 text-xs text-muted-foreground">Se muestran los primeros 200.</p>
        ) : null}
      </div>
    </FormDialog>
  );
}
