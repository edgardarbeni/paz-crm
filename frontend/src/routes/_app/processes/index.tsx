import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { useState } from "react";
import {
  createProcessMutation,
  listProcessesOptions,
  listProcessesQueryKey,
} from "@/client/@tanstack/react-query.gen";
import type { ProcessIn, ProcessOut } from "@/client/types.gen";
import { zProcessIn } from "@/client/zod.gen";
import { AsyncCombobox, type ComboItem } from "@/components/async-combobox";
import { type Column, DataTable } from "@/components/data/data-table";
import { FieldShell, submitOnModEnter, useAppForm } from "@/components/form/form";
import { FormDialog } from "@/components/form-dialog";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { GeoName } from "@/features/candidacies/geo-name";
import { useHotkey } from "@/hooks/use-hotkey";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";
import { blanksToNull, formSchema } from "@/lib/forms";
import { ELECTION_LEVEL, formatDate, options, PROCESS_STATUS } from "@/lib/labels";
import { GEO_SEARCH_HINTS, searchGeoItems } from "@/lib/search";

export const Route = createFileRoute("/_app/processes/")({ component: ProcessesPage });

const columns: Column<ProcessOut>[] = [
  {
    id: "name",
    header: "Proceso",
    cell: ({ row }) => <span className="font-medium">{row.original.name}</span>,
  },
  { id: "year", header: "Año", cell: ({ row }) => row.original.election_year },
  { id: "level", header: "Ámbito", cell: ({ row }) => ELECTION_LEVEL[row.original.election_level] },
  {
    id: "state",
    header: "Estado",
    cell: ({ row }) =>
      row.original.state_id ? <GeoName level="state" id={row.original.state_id} /> : "—",
  },
  { id: "date", header: "Jornada", cell: ({ row }) => formatDate(row.original.election_date) },
  {
    id: "status",
    header: "Estatus",
    cell: ({ row }) => <Badge variant="secondary">{PROCESS_STATUS[row.original.status]}</Badge>,
  },
];

function ProcessesPage() {
  const can = useCan();
  const navigate = useNavigate();
  const processes = useQuery(listProcessesOptions());
  const [creating, setCreating] = useState(false);
  const manage = can(Perm.PROCESS_MANAGE);
  useHotkey("n", () => setCreating(true), manage);
  return (
    <section>
      <PageHeader
        title="Procesos electorales"
        description="Cada proceso define qué cargos van a elección, la integración de ayuntamientos y las reglas de validación."
        actions={
          manage ? (
            <Button onClick={() => setCreating(true)}>
              <Plus aria-hidden /> Nuevo proceso
            </Button>
          ) : null
        }
      />
      <ProblemAlert error={processes.error} />
      <DataTable
        caption="Procesos electorales"
        columns={columns}
        data={processes.data}
        isLoading={processes.isPending}
        getRowId={(r) => r.id}
        onActivate={(row) =>
          navigate({ to: "/processes/$processId", params: { processId: row.id } })
        }
      />
      {creating ? <ProcessDialog onClose={() => setCreating(false)} /> : null}
    </section>
  );
}

function ProcessDialog({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [state, setState] = useState<ComboItem | null>(null);
  const create = useMutation({
    ...createProcessMutation(),
    onSuccess: (process) => {
      queryClient.invalidateQueries({ queryKey: listProcessesQueryKey() });
      navigate({ to: "/processes/$processId", params: { processId: process.id } });
    },
  });
  const form = useAppForm({
    defaultValues: {
      name: "",
      election_year: new Date().getFullYear() + 1,
      process_type: "ordinary",
      election_level: "local",
      election_date: "",
    } as Omit<ProcessIn, "election_date"> & { election_date: string },
    validators: { onSubmit: formSchema(zProcessIn.omit({ state_id: true })) },
    onSubmit: async ({ value }) => {
      const body = {
        ...blanksToNull(value),
        state_id: value.election_level === "local" ? state?.id : null,
      };
      await create.mutateAsync({ body: body as ProcessIn }).catch(() => {});
    },
  });
  return (
    <FormDialog open onOpenChange={(open) => !open && onClose()} title="Nuevo proceso electoral">
      <form
        className="grid gap-4"
        noValidate
        onKeyDown={submitOnModEnter}
        onSubmit={(event) => {
          event.preventDefault();
          form.handleSubmit();
        }}
      >
        <ProblemAlert error={create.error} />
        <form.AppField name="name">
          {(field) => (
            <field.TextField
              label="Nombre"
              placeholder="Proceso Electoral Local 2027"
              autoFocus
              required
            />
          )}
        </form.AppField>
        <div className="grid grid-cols-2 gap-3">
          <form.AppField name="election_year">
            {(field) => <field.NumberField label="Año" min={2000} max={2100} required />}
          </form.AppField>
          <form.AppField name="election_date">
            {(field) => <field.TextField label="Jornada electoral" type="date" />}
          </form.AppField>
          <form.AppField name="process_type">
            {(field) => (
              <field.SelectField
                label="Tipo"
                options={[
                  { value: "ordinary", label: "Ordinario" },
                  { value: "extraordinary", label: "Extraordinario" },
                ]}
                required
              />
            )}
          </form.AppField>
          <form.AppField name="election_level">
            {(field) => (
              <field.SelectField label="Ámbito" options={options(ELECTION_LEVEL)} required />
            )}
          </form.AppField>
        </div>
        <form.Subscribe selector={(s) => s.values.election_level}>
          {(level) =>
            level === "local" ? (
              <FieldShell id="process-state" label="Estado" required>
                <AsyncCombobox
                  id="process-state"
                  label="Estado"
                  value={state}
                  onChange={setState}
                  queryKey={["geo-search", "state"]}
                  search={(term) => searchGeoItems(term, ["state"])}
                  minChars={1}
                  placeholder={GEO_SEARCH_HINTS.state}
                />
              </FieldShell>
            ) : null
          }
        </form.Subscribe>
        <form.AppForm>
          <form.SubmitButton>Crear proceso</form.SubmitButton>
        </form.AppForm>
      </form>
    </FormDialog>
  );
}
