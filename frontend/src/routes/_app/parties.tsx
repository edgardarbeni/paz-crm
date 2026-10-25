import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { useState } from "react";
import {
  createPartyMutation,
  listPartiesOptions,
  listPartiesQueryKey,
  updatePartyMutation,
} from "@/client/@tanstack/react-query.gen";
import type { PartyOut } from "@/client/types.gen";
import { zPartyIn } from "@/client/zod.gen";
import { type Column, DataTable } from "@/components/data/data-table";
import { submitOnModEnter, useAppForm } from "@/components/form/form";
import { FormDialog } from "@/components/form-dialog";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useHotkey } from "@/hooks/use-hotkey";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";
import { blanksToNull, formSchema } from "@/lib/forms";

export const Route = createFileRoute("/_app/parties")({ component: PartiesPage });

const columns: Column<PartyOut>[] = [
  {
    id: "acronym",
    header: "Siglas",
    cell: ({ row }) => (
      <span className="inline-flex items-center gap-2 font-medium">
        <span
          aria-hidden
          className="size-3 rounded-full border"
          style={{ background: row.original.color_hex ?? "transparent" }}
        />
        {row.original.acronym}
      </span>
    ),
  },
  { id: "name", header: "Nombre", cell: ({ row }) => row.original.name },
  {
    id: "own",
    header: "",
    cell: ({ row }) => (row.original.is_own_party ? <Badge>Partido propio</Badge> : null),
  },
];

function PartiesPage() {
  const can = useCan();
  const parties = useQuery(listPartiesOptions());
  const [editing, setEditing] = useState<PartyOut | "new" | null>(null);
  const manage = can(Perm.CATALOG_MANAGE);
  useHotkey("n", () => setEditing("new"), manage);

  return (
    <section>
      <PageHeader
        title="Partidos"
        description="Partidos políticos que postulan candidaturas (solos o en coalición)."
        actions={
          manage ? (
            <Button onClick={() => setEditing("new")}>
              <Plus aria-hidden /> Nuevo partido
            </Button>
          ) : null
        }
      />
      <ProblemAlert error={parties.error} />
      <DataTable
        caption="Partidos"
        columns={columns}
        data={parties.data}
        isLoading={parties.isPending}
        getRowId={(row) => row.id}
        onActivate={manage ? (row) => setEditing(row) : undefined}
      />
      {editing ? (
        <PartyDialog party={editing === "new" ? null : editing} onClose={() => setEditing(null)} />
      ) : null}
    </section>
  );
}

function PartyDialog({ party, onClose }: { party: PartyOut | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const onSuccess = () => {
    queryClient.invalidateQueries({ queryKey: listPartiesQueryKey() });
    onClose();
  };
  const create = useMutation({ ...createPartyMutation(), onSuccess });
  const update = useMutation({ ...updatePartyMutation(), onSuccess });
  const error = create.error ?? update.error;
  const form = useAppForm({
    defaultValues: {
      acronym: party?.acronym ?? "",
      name: party?.name ?? "",
      color_hex: party?.color_hex ?? "",
      logo_uri: party?.logo_uri ?? "",
      is_own_party: party?.is_own_party ?? false,
    },
    validators: { onSubmit: formSchema(zPartyIn) },
    onSubmit: async ({ value }) => {
      const body = blanksToNull(value);
      await (party
        ? update.mutateAsync({ path: { party_id: party.id }, body })
        : create.mutateAsync({ body })
      ).catch(() => {});
    },
  });
  return (
    <FormDialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={party ? "Editar partido" : "Nuevo partido"}
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
        <ProblemAlert error={error} />
        <div className="grid grid-cols-[8rem_1fr] gap-3">
          <form.AppField name="acronym">
            {(field) => (
              <field.TextField
                label="Siglas"
                autoFocus
                required
                normalize={(v) => v.toUpperCase()}
              />
            )}
          </form.AppField>
          <form.AppField name="name">
            {(field) => <field.TextField label="Nombre" required />}
          </form.AppField>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <form.AppField name="color_hex">
            {(field) => (
              <field.TextField label="Color" placeholder="#7A1F5C" description="Formato #RRGGBB" />
            )}
          </form.AppField>
          <form.AppField name="logo_uri">
            {(field) => <field.TextField label="Logo (URL)" />}
          </form.AppField>
        </div>
        <form.AppField name="is_own_party">
          {(field) => <field.CheckboxField label="Es el partido propio" />}
        </form.AppField>
        <form.AppForm>
          <form.SubmitButton>Guardar</form.SubmitButton>
        </form.AppForm>
      </form>
    </FormDialog>
  );
}
