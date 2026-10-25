import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { useState } from "react";
import {
  createRoleMutation,
  listRolesOptions,
  listRolesQueryKey,
} from "@/client/@tanstack/react-query.gen";
import type { RoleOut } from "@/client/types.gen";
import { zRoleCreateRequest } from "@/client/zod.gen";
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

export const Route = createFileRoute("/_app/roles/")({ component: RolesPage });

const columns: Column<RoleOut>[] = [
  {
    id: "name",
    header: "Rol",
    cell: ({ row }) => (
      <div>
        <div className="font-medium">{row.original.name}</div>
        <div className="text-xs text-muted-foreground">{row.original.description}</div>
      </div>
    ),
  },
  {
    id: "flags",
    header: "",
    cell: ({ row }) => (
      <span className="flex flex-wrap gap-1">
        {row.original.is_system ? <Badge variant="outline">Del sistema</Badge> : null}
        {row.original.requires_mfa ? <Badge variant="secondary">Exige 2FA</Badge> : null}
        {row.original.grants_all ? <Badge>Todos los permisos</Badge> : null}
      </span>
    ),
  },
  {
    id: "permissions",
    header: "Permisos",
    cell: ({ row }) => (row.original.grants_all ? "Todos" : row.original.permissions.length),
  },
  { id: "users", header: "Usuarios", cell: ({ row }) => row.original.user_count },
];

function RolesPage() {
  const can = useCan();
  const navigate = useNavigate();
  const roles = useQuery(listRolesOptions());
  const [creating, setCreating] = useState(false);
  useHotkey("n", () => setCreating(true), can(Perm.ROLE_CREATE));
  return (
    <section>
      <PageHeader
        title="Roles y permisos"
        description="Cada rol agrupa permisos por módulo y acción. El alcance geográfico se asigna por usuario."
        actions={
          can(Perm.ROLE_CREATE) ? (
            <Button onClick={() => setCreating(true)}>
              <Plus aria-hidden /> Nuevo rol
            </Button>
          ) : null
        }
      />
      <ProblemAlert error={roles.error} />
      <DataTable
        caption="Roles"
        columns={columns}
        data={roles.data}
        isLoading={roles.isPending}
        getRowId={(r) => r.id}
        onActivate={(row) => navigate({ to: "/roles/$roleId", params: { roleId: row.id } })}
      />
      {creating ? <CreateRoleDialog onClose={() => setCreating(false)} /> : null}
    </section>
  );
}

function CreateRoleDialog({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const create = useMutation({
    ...createRoleMutation(),
    onSuccess: (role) => {
      queryClient.invalidateQueries({ queryKey: listRolesQueryKey() });
      navigate({ to: "/roles/$roleId", params: { roleId: role.id } });
    },
  });
  const form = useAppForm({
    defaultValues: { code: "", name: "", description: "", requires_mfa: false },
    validators: { onSubmit: formSchema(zRoleCreateRequest) },
    onSubmit: async ({ value }) => {
      await create
        .mutateAsync({ body: { ...blanksToNull(value), permissions: [] } })
        .catch(() => {});
    },
  });
  return (
    <FormDialog
      open
      onOpenChange={(o) => !o && onClose()}
      title="Nuevo rol"
      description="Después elige sus permisos."
    >
      <form
        className="grid gap-4"
        noValidate
        onKeyDown={submitOnModEnter}
        onSubmit={(e) => {
          e.preventDefault();
          form.handleSubmit();
        }}
      >
        <ProblemAlert error={create.error} />
        <form.AppField name="name">
          {(f) => <f.TextField label="Nombre" autoFocus required />}
        </form.AppField>
        <form.AppField name="code">
          {(f) => (
            <f.TextField
              label="Código"
              required
              description="Minúsculas y guion bajo, p. ej. enlace_distrital"
              normalize={(v) => v.toLowerCase().replace(/[^a-z0-9_]/g, "_")}
            />
          )}
        </form.AppField>
        <form.AppField name="description">
          {(f) => <f.TextareaField label="Descripción" />}
        </form.AppField>
        <form.AppField name="requires_mfa">
          {(f) => <f.CheckboxField label="Exige segundo factor (TOTP)" />}
        </form.AppField>
        <form.AppForm>
          <form.SubmitButton>Crear rol</form.SubmitButton>
        </form.AppForm>
      </form>
    </FormDialog>
  );
}
