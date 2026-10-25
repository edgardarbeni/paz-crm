import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  deleteRoleMutation,
  getRoleOptions,
  getRoleQueryKey,
  listPermissionsOptions,
  listRolesQueryKey,
  setRolePermissionsMutation,
  updateRoleMutation,
} from "@/client/@tanstack/react-query.gen";
import type { PermissionOut, RoleOut } from "@/client/types.gen";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { LabeledToggle } from "@/components/labeled-toggle";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";

export const Route = createFileRoute("/_app/roles/$roleId")({ component: RolePage });

const MODULES: Record<string, string> = {
  identity: "Identidad",
  audit: "Auditoría",
  geography: "Geografía",
  people: "Personas",
  candidacies: "Candidaturas",
};

function RolePage() {
  const { roleId } = Route.useParams();
  const can = useCan();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const role = useQuery(getRoleOptions({ path: { role_id: roleId } }));
  const remove = useMutation({
    ...deleteRoleMutation(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: listRolesQueryKey() });
      toast.success("Rol eliminado.");
      navigate({ to: "/roles" });
    },
  });
  if (role.isError) return <ProblemAlert error={role.error} />;
  const r = role.data;
  if (!r) return <p className="text-muted-foreground">Cargando…</p>;
  return (
    <section className="max-w-4xl">
      <PageHeader
        title={r.name}
        description={`${r.code} · ${r.user_count} usuario(s)`}
        actions={
          can(Perm.ROLE_DELETE) && !r.is_system ? (
            <ConfirmDialog
              trigger={<Button variant="outline">Eliminar rol</Button>}
              title="¿Eliminar el rol?"
              description="Solo se pueden eliminar roles sin usuarios asignados."
              confirmLabel="Eliminar"
              destructive
              onConfirm={() => remove.mutate({ path: { role_id: roleId } })}
            />
          ) : null
        }
      />
      <div className="space-y-6">
        <ProblemAlert error={remove.error} />
        <RoleDetails role={r} editable={can(Perm.ROLE_UPDATE) && !r.is_system} />
        <PermissionsMatrix role={r} editable={can(Perm.ROLE_UPDATE) && !r.grants_all} />
      </div>
    </section>
  );
}

function RoleDetails({ role, editable }: { role: RoleOut; editable: boolean }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(role.name);
  const [description, setDescription] = useState(role.description ?? "");
  const [requiresMfa, setRequiresMfa] = useState(role.requires_mfa);
  const update = useMutation({
    ...updateRoleMutation(),
    onSuccess: (data) => {
      queryClient.setQueryData(getRoleQueryKey({ path: { role_id: role.id } }), data);
      toast.success("Rol actualizado.");
    },
  });
  return (
    <Card>
      <CardContent>
        <form
          className="grid gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            update.mutate({
              path: { role_id: role.id },
              body: {
                name: name.trim(),
                description: description.trim() || null,
                requires_mfa: requiresMfa,
              },
            });
          }}
        >
          <ProblemAlert error={update.error} />
          <div className="grid gap-1.5">
            <Label htmlFor="role-name">Nombre</Label>
            <Input
              id="role-name"
              value={name}
              disabled={!editable}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="role-description">Descripción</Label>
            <Textarea
              id="role-description"
              value={description}
              disabled={!editable}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <LabeledToggle
            kind="switch"
            checked={requiresMfa}
            disabled={!editable}
            onCheckedChange={setRequiresMfa}
          >
            Exige segundo factor (TOTP)
          </LabeledToggle>
          {editable ? (
            <Button
              type="submit"
              variant="outline"
              className="justify-self-start"
              disabled={update.isPending}
            >
              Guardar
            </Button>
          ) : null}
        </form>
      </CardContent>
    </Card>
  );
}

function PermissionsMatrix({ role, editable }: { role: RoleOut; editable: boolean }) {
  const queryClient = useQueryClient();
  const permissions = useQuery(listPermissionsOptions());
  const [selected, setSelected] = useState<string[]>(role.permissions);
  useEffect(() => setSelected(role.permissions), [role.permissions]);
  const save = useMutation({
    ...setRolePermissionsMutation(),
    onSuccess: (data) => {
      queryClient.setQueryData(getRoleQueryKey({ path: { role_id: role.id } }), data);
      toast.success("Permisos guardados.");
    },
  });
  const byModule = new Map<string, PermissionOut[]>();
  for (const p of permissions.data ?? [])
    byModule.set(p.module, [...(byModule.get(p.module) ?? []), p]);
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Permisos</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {role.grants_all ? (
          <p className="text-sm">Este rol tiene todos los permisos del sistema.</p>
        ) : null}
        <ProblemAlert error={save.error ?? permissions.error} />
        {[...byModule.entries()].map(([module, items]) => (
          <fieldset key={module} className="space-y-2">
            <legend className="text-sm font-semibold">{MODULES[module] ?? module}</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {items.map((p) => (
                <LabeledToggle
                  key={p.code}
                  disabled={!editable}
                  checked={role.grants_all || selected.includes(p.code)}
                  onCheckedChange={(c) =>
                    setSelected(c ? [...selected, p.code] : selected.filter((x) => x !== p.code))
                  }
                >
                  <span>
                    {p.description}
                    <code className="block text-xs text-muted-foreground">{p.code}</code>
                  </span>
                </LabeledToggle>
              ))}
            </div>
          </fieldset>
        ))}
        {editable ? (
          <Button
            disabled={save.isPending}
            onClick={() =>
              save.mutate({ path: { role_id: role.id }, body: { permissions: selected } })
            }
          >
            Guardar permisos
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}
