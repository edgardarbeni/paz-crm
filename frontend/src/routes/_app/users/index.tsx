import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { useState } from "react";
import { z } from "zod";
import {
  inviteUserMutation,
  listRolesOptions,
  listUsersOptions,
} from "@/client/@tanstack/react-query.gen";
import type { UserOut, UserStatus } from "@/client/types.gen";
import { zUserInviteRequest } from "@/client/zod.gen";
import { type Column, DataTable } from "@/components/data/data-table";
import { useCursorPager } from "@/components/data/use-cursor-pager";
import { submitOnModEnter, useAppForm } from "@/components/form/form";
import { FormDialog } from "@/components/form-dialog";
import { LabeledToggle } from "@/components/labeled-toggle";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { SearchInput } from "@/components/search-input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useDebounced } from "@/hooks/use-debounced";
import { useHotkey } from "@/hooks/use-hotkey";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";
import { formatDateTime, USER_STATUS } from "@/lib/labels";

export const Route = createFileRoute("/_app/users/")({
  validateSearch: z.object({
    status: z.enum(["invited", "active", "disabled"]).optional(),
    role_id: z.string().optional(),
    sort: z.string().optional(),
  }),
  component: UsersPage,
});

const columns: Column<UserOut>[] = [
  {
    id: "name",
    header: "Nombre",
    sortKey: "full_name",
    cell: ({ row }) => (
      <div>
        <div className="font-medium">{row.original.full_name}</div>
        <div className="text-xs text-muted-foreground">{row.original.email}</div>
      </div>
    ),
  },
  {
    id: "roles",
    header: "Roles",
    cell: ({ row }) => row.original.roles.map((r) => r.name).join(", ") || "—",
  },
  {
    id: "status",
    header: "Estatus",
    cell: ({ row }) => (
      <span className="flex gap-1">
        <Badge variant={row.original.status === "active" ? "secondary" : "outline"}>
          {USER_STATUS[row.original.status]}
        </Badge>
        {row.original.locked_until && new Date(row.original.locked_until) > new Date() ? (
          <Badge variant="destructive">Bloqueado</Badge>
        ) : null}
      </span>
    ),
  },
  { id: "mfa", header: "2FA", cell: ({ row }) => (row.original.mfa_enabled ? "Sí" : "No") },
  {
    id: "last",
    header: "Último acceso",
    sortKey: "last_login_at",
    cell: ({ row }) => formatDateTime(row.original.last_login_at),
  },
];

function UsersPage() {
  const filters = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const can = useCan();
  const roles = useQuery(listRolesOptions());
  const [term, setTerm] = useState("");
  const q = useDebounced(term.trim(), 300);
  const [inviting, setInviting] = useState(false);
  const { cursor, pager } = useCursorPager(JSON.stringify([filters, q]));
  const users = useQuery(
    listUsersOptions({
      query: {
        ...filters,
        status: filters.status as UserStatus | undefined,
        q: q || undefined,
        cursor,
        limit: 50,
      },
    }),
  );
  const create = can(Perm.USER_CREATE);
  useHotkey("n", () => setInviting(true), create);

  return (
    <section>
      <PageHeader
        title="Usuarios"
        description="Solo ves y administras usuarios cuyo alcance geográfico está dentro del tuyo."
        actions={
          create ? (
            <Button onClick={() => setInviting(true)}>
              <Plus aria-hidden /> Invitar usuario
            </Button>
          ) : null
        }
      />
      <div className="mb-4 flex flex-wrap gap-2">
        <SearchInput value={term} onChange={setTerm} label="Buscar por nombre o correo" />
        <select
          aria-label="Estatus"
          value={filters.status ?? ""}
          onChange={(e) =>
            navigate({ search: (p) => ({ ...p, status: (e.target.value || undefined) as never }) })
          }
          className="h-8 rounded-lg border border-input bg-transparent px-2 text-sm"
        >
          <option value="">Todos los estatus</option>
          {(["invited", "active", "disabled"] as const).map((s) => (
            <option key={s} value={s}>
              {USER_STATUS[s]}
            </option>
          ))}
        </select>
        <select
          aria-label="Rol"
          value={filters.role_id ?? ""}
          onChange={(e) =>
            navigate({ search: (p) => ({ ...p, role_id: e.target.value || undefined }) })
          }
          className="h-8 rounded-lg border border-input bg-transparent px-2 text-sm"
        >
          <option value="">Todos los roles</option>
          {(roles.data ?? []).map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </select>
      </div>
      <ProblemAlert error={users.error} />
      <DataTable
        caption="Usuarios"
        columns={columns}
        data={users.data?.items}
        isLoading={users.isPending}
        getRowId={(r) => r.id}
        pager={pager(users.data)}
        sort={filters.sort ?? "full_name"}
        onSortChange={(sort) => navigate({ search: (p) => ({ ...p, sort }) })}
        onActivate={(row) => navigate({ to: "/users/$userId", params: { userId: row.id } })}
      />
      {inviting ? <InviteDialog onClose={() => setInviting(false)} /> : null}
    </section>
  );
}

function InviteDialog({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const roles = useQuery(listRolesOptions());
  const [roleIds, setRoleIds] = useState<string[]>([]);
  const invite = useMutation({
    ...inviteUserMutation(),
    onSuccess: (user) => {
      queryClient.invalidateQueries({ queryKey: ["listUsers"] });
      navigate({ to: "/users/$userId", params: { userId: user.id } });
    },
  });
  const form = useAppForm({
    defaultValues: { email: "", full_name: "" },
    validators: { onSubmit: zUserInviteRequest.omit({ role_ids: true }) },
    onSubmit: async ({ value }) => {
      await invite.mutateAsync({ body: { ...value, role_ids: roleIds } }).catch(() => {});
    },
  });
  return (
    <FormDialog
      open
      onOpenChange={(o) => !o && onClose()}
      title="Invitar usuario"
      description="Recibirá un correo para definir su contraseña. Después asigna su alcance geográfico."
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
        <ProblemAlert error={invite.error} />
        <form.AppField name="full_name">
          {(f) => <f.TextField label="Nombre completo" autoFocus required />}
        </form.AppField>
        <form.AppField name="email">
          {(f) => <f.TextField label="Correo" type="email" required />}
        </form.AppField>
        <fieldset className="grid gap-2">
          <legend className="mb-1 text-sm font-medium">Roles</legend>
          {(roles.data ?? []).map((role) => (
            <LabeledToggle
              key={role.id}
              checked={roleIds.includes(role.id)}
              onCheckedChange={(c) =>
                setRoleIds(c ? [...roleIds, role.id] : roleIds.filter((id) => id !== role.id))
              }
            >
              {role.name}
              {role.requires_mfa ? (
                <span className="text-xs text-muted-foreground">(exige 2FA)</span>
              ) : null}
            </LabeledToggle>
          ))}
        </fieldset>
        <form.AppForm>
          <form.SubmitButton>Enviar invitación</form.SubmitButton>
        </form.AppForm>
      </form>
    </FormDialog>
  );
}
