import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { useState } from "react";
import {
  createOfficeTypeMutation,
  listOfficeTypesOptions,
  listOfficeTypesQueryKey,
  updateOfficeTypeMutation,
} from "@/client/@tanstack/react-query.gen";
import type { OfficeTypeIn, OfficeTypeOut } from "@/client/types.gen";
import { zOfficeTypeIn } from "@/client/zod.gen";
import { type Column, DataTable } from "@/components/data/data-table";
import { submitOnModEnter, useAppForm } from "@/components/form/form";
import { FormDialog } from "@/components/form-dialog";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Button } from "@/components/ui/button";
import { useHotkey } from "@/hooks/use-hotkey";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";
import { blanksToNull, formSchema } from "@/lib/forms";
import {
  ELECTION_LEVEL,
  GEO_LEVEL_LABELS,
  NOMINATION_KIND,
  options,
  PRINCIPLE,
} from "@/lib/labels";

export const Route = createFileRoute("/_app/office-types")({ component: OfficeTypesPage });

const columns: Column<OfficeTypeOut>[] = [
  {
    id: "name",
    header: "Cargo",
    cell: ({ row }) => <span className="font-medium">{row.original.name}</span>,
  },
  {
    id: "code",
    header: "Código",
    cell: ({ row }) => <code className="text-xs">{row.original.code}</code>,
  },
  { id: "level", header: "Ámbito", cell: ({ row }) => ELECTION_LEVEL[row.original.election_level] },
  {
    id: "geo",
    header: "Nivel geográfico",
    cell: ({ row }) => GEO_LEVEL_LABELS[row.original.geographic_level],
  },
  { id: "principle", header: "Principio", cell: ({ row }) => row.original.principle.toUpperCase() },
  { id: "kind", header: "Tipo", cell: ({ row }) => NOMINATION_KIND[row.original.nomination_kind] },
  {
    id: "positions",
    header: "Posiciones",
    cell: ({ row }) => row.original.default_positions ?? "—",
  },
  {
    id: "substitute",
    header: "Suplencia",
    cell: ({ row }) => (row.original.has_substitute ? "Sí" : "No"),
  },
];

const GEO_OPTIONS = options(GEO_LEVEL_LABELS).filter((o) =>
  [
    "national",
    "electoral_region",
    "state",
    "federal_district",
    "local_district",
    "municipality",
  ].includes(o.value),
);

function OfficeTypesPage() {
  const can = useCan();
  const offices = useQuery(listOfficeTypesOptions());
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<OfficeTypeOut | null>(null);
  const manage = can(Perm.CATALOG_MANAGE);
  useHotkey("n", () => setCreating(true), manage);
  return (
    <section>
      <PageHeader
        title="Cargos"
        description="Catálogo de cargos de elección. Agregar un cargo no requiere cambios al sistema; cada proceso decide cuáles van a elección."
        actions={
          manage ? (
            <Button onClick={() => setCreating(true)}>
              <Plus aria-hidden /> Nuevo cargo
            </Button>
          ) : null
        }
      />
      <ProblemAlert error={offices.error} />
      <DataTable
        caption="Cargos"
        columns={columns}
        data={offices.data}
        isLoading={offices.isPending}
        getRowId={(r) => r.id}
        onActivate={manage ? setEditing : undefined}
      />
      {creating ? <OfficeTypeDialog onClose={() => setCreating(false)} /> : null}
      {editing ? <EditOfficeTypeDialog office={editing} onClose={() => setEditing(null)} /> : null}
    </section>
  );
}

function OfficeTypeDialog({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const create = useMutation({
    ...createOfficeTypeMutation(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: listOfficeTypesQueryKey() });
      onClose();
    },
  });
  const form = useAppForm({
    defaultValues: {
      code: "",
      name: "",
      election_level: "local",
      geographic_level: "municipality",
      principle: "mr",
      nomination_kind: "single",
      default_positions: null,
      has_substitute: true,
      sort_order: 100,
    } as OfficeTypeIn,
    validators: { onSubmit: formSchema(zOfficeTypeIn) },
    onSubmit: async ({ value }) => {
      await create.mutateAsync({ body: blanksToNull(value) }).catch(() => {});
    },
  });
  return (
    <FormDialog open onOpenChange={(open) => !open && onClose()} title="Nuevo cargo" wide>
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
        <div className="grid gap-3 sm:grid-cols-2">
          <form.AppField name="name">
            {(field) => <field.TextField label="Nombre" autoFocus required />}
          </form.AppField>
          <form.AppField name="code">
            {(field) => (
              <field.TextField
                label="Código"
                required
                description="Minúsculas y guion bajo, p. ej. presidencia_comunidad"
                normalize={(v) => v.toLowerCase().replace(/[^a-z0-9_]/g, "_")}
              />
            )}
          </form.AppField>
          <form.AppField name="election_level">
            {(field) => (
              <field.SelectField label="Ámbito" options={options(ELECTION_LEVEL)} required />
            )}
          </form.AppField>
          <form.AppField name="geographic_level">
            {(field) => (
              <field.SelectField label="Nivel geográfico" options={GEO_OPTIONS} required />
            )}
          </form.AppField>
          <form.AppField name="principle">
            {(field) => (
              <field.SelectField label="Principio" options={options(PRINCIPLE)} required />
            )}
          </form.AppField>
          <form.AppField name="nomination_kind">
            {(field) => (
              <field.SelectField
                label="Tipo de postulación"
                options={options(NOMINATION_KIND)}
                required
              />
            )}
          </form.AppField>
          <form.AppField name="default_positions">
            {(field) => <field.NumberField label="Posiciones por defecto" min={1} max={500} />}
          </form.AppField>
          <form.AppField name="sort_order">
            {(field) => <field.NumberField label="Orden" min={0} />}
          </form.AppField>
        </div>
        <form.AppField name="has_substitute">
          {(field) => (
            <field.CheckboxField label="Lleva suplencia (fórmula propietaria + suplente)" />
          )}
        </form.AppField>
        <form.AppForm>
          <form.SubmitButton>Guardar</form.SubmitButton>
        </form.AppForm>
      </form>
    </FormDialog>
  );
}

/** Code, levels, principle and kind stay fixed once created; nominations depend on them. */
function EditOfficeTypeDialog({ office, onClose }: { office: OfficeTypeOut; onClose: () => void }) {
  const queryClient = useQueryClient();
  const update = useMutation({
    ...updateOfficeTypeMutation(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: listOfficeTypesQueryKey() });
      onClose();
    },
  });
  const form = useAppForm({
    defaultValues: {
      name: office.name,
      default_positions: office.default_positions ?? null,
      has_substitute: office.has_substitute ?? true,
      sort_order: office.sort_order ?? 100,
    },
    onSubmit: async ({ value }) => {
      await update
        .mutateAsync({ path: { office_type_id: office.id }, body: value })
        .catch(() => {});
    },
  });
  return (
    <FormDialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={`Editar ${office.name}`}
      description={`${office.code} · ${GEO_LEVEL_LABELS[office.geographic_level]} · ${NOMINATION_KIND[office.nomination_kind]}`}
    >
      <form
        className="grid gap-4"
        noValidate
        onKeyDown={submitOnModEnter}
        onSubmit={(event) => {
          event.preventDefault();
          form.handleSubmit();
        }}
      >
        <ProblemAlert error={update.error} />
        <form.AppField name="name">
          {(field) => <field.TextField label="Nombre" autoFocus required />}
        </form.AppField>
        <div className="grid grid-cols-2 gap-3">
          <form.AppField name="default_positions">
            {(field) => <field.NumberField label="Posiciones por defecto" min={1} max={500} />}
          </form.AppField>
          <form.AppField name="sort_order">
            {(field) => <field.NumberField label="Orden" min={0} />}
          </form.AppField>
        </div>
        <form.AppField name="has_substitute">
          {(field) => <field.CheckboxField label="Lleva suplencia" />}
        </form.AppField>
        <form.AppForm>
          <form.SubmitButton>Guardar</form.SubmitButton>
        </form.AppForm>
      </form>
    </FormDialog>
  );
}
