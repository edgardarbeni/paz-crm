import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  activateUserMutation,
  disableUserMutation,
  getUserOptions,
  getUserQueryKey,
  listRolesOptions,
  listUserSessionsOptions,
  listUserSessionsQueryKey,
  resendInvitationMutation,
  resetUserMfaMutation,
  revokeUserSessionsMutation,
  setUserRolesMutation,
  unlockUserMutation,
  updateUserMutation,
} from "@/client/@tanstack/react-query.gen";
import type { UserOut } from "@/client/types.gen";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { LabeledToggle } from "@/components/labeled-toggle";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScopesEditor } from "@/features/identity/scopes-editor";
import { SessionsTable } from "@/features/identity/sessions-table";
import { BranchesEditor } from "@/features/peace-movement/branches-editor";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";
import { formatDateTime, USER_STATUS } from "@/lib/labels";

export const Route = createFileRoute("/_app/users/$userId")({ component: UserPage });

function UserPage() {
  const { userId } = Route.useParams();
  const can = useCan();
  const queryClient = useQueryClient();
  const key = getUserQueryKey({ path: { user_id: userId } });
  const user = useQuery(getUserOptions({ path: { user_id: userId } }));
  const [error, setError] = useState<unknown>(null);
  const onUser = (message: string) => ({
    onSuccess: (data: UserOut) => {
      queryClient.setQueryData(key, data);
      queryClient.invalidateQueries({ queryKey: ["listUsers"] });
      toast.success(message);
    },
    onError: setError,
  });
  const disable = useMutation({
    ...disableUserMutation(),
    ...onUser("Usuario deshabilitado; sus sesiones se cerraron."),
  });
  const activate = useMutation({ ...activateUserMutation(), ...onUser("Usuario activado.") });
  const unlock = useMutation({ ...unlockUserMutation(), ...onUser("Usuario desbloqueado.") });
  const resetMfa = useMutation({
    ...resetUserMfaMutation(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: key });
      toast.success("2FA restablecido: lo configurará en su próximo acceso.");
    },
    onError: setError,
  });
  const resend = useMutation({
    ...resendInvitationMutation(),
    onSuccess: () => toast.success("Invitación reenviada."),
    onError: setError,
  });
  const revoke = useMutation({
    ...revokeUserSessionsMutation(),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: listUserSessionsQueryKey({ path: { user_id: userId } }),
      });
      toast.success("Sesiones cerradas.");
    },
    onError: setError,
  });
  if (user.isError) return <ProblemAlert error={user.error} />;
  const u = user.data;
  if (!u) return <p className="text-muted-foreground">Cargando…</p>;
  const path = { path: { user_id: userId } };
  const locked = !!u.locked_until && new Date(u.locked_until) > new Date();

  return (
    <section className="max-w-4xl">
      <PageHeader
        title={u.full_name}
        description={`${u.email} · Alta ${formatDateTime(u.created_at)} · Último acceso ${formatDateTime(u.last_login_at)}`}
        actions={
          <>
            <Badge variant="secondary">{USER_STATUS[u.status]}</Badge>
            {locked ? <Badge variant="destructive">Bloqueado</Badge> : null}
            {u.status === "invited" && can(Perm.USER_CREATE) ? (
              <Button variant="outline" onClick={() => resend.mutate(path)}>
                Reenviar invitación
              </Button>
            ) : null}
            {locked && can(Perm.USER_DISABLE) ? (
              <Button variant="outline" onClick={() => unlock.mutate(path)}>
                Desbloquear
              </Button>
            ) : null}
            {can(Perm.USER_DISABLE) && u.status === "active" ? (
              <ConfirmDialog
                trigger={<Button variant="outline">Deshabilitar</Button>}
                title="¿Deshabilitar el usuario?"
                description="No podrá iniciar sesión y se cierran todas sus sesiones."
                confirmLabel="Deshabilitar"
                destructive
                onConfirm={() => disable.mutate(path)}
              />
            ) : null}
            {can(Perm.USER_DISABLE) && u.status === "disabled" ? (
              <Button variant="outline" onClick={() => activate.mutate(path)}>
                Activar
              </Button>
            ) : null}
          </>
        }
      />
      <div className="space-y-6">
        <ProblemAlert error={error} />
        {can(Perm.USER_UPDATE) ? <NameCard user={u} /> : null}
        <RolesCard user={u} editable={can(Perm.USER_ASSIGN_ROLES)} />
        <Card>
          <CardHeader>
            <CardTitle>
              <h2>Alcance geográfico</h2>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ScopesEditor userId={userId} editable={can(Perm.USER_ASSIGN_SCOPES)} />
          </CardContent>
        </Card>
        {can(Perm.PEACE_MEMBER_READ) ? (
          <Card>
            <CardHeader>
              <CardTitle>
                <h2>Ramas del Movimiento de Paz</h2>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <BranchesEditor userId={userId} editable={can(Perm.USER_ASSIGN_SCOPES)} />
            </CardContent>
          </Card>
        ) : null}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>
              <h2>Seguridad</h2>
            </CardTitle>
            <div className="flex gap-2">
              {can(Perm.USER_RESET_MFA) && u.mfa_enabled ? (
                <ConfirmDialog
                  trigger={
                    <Button variant="outline" size="sm">
                      Restablecer 2FA
                    </Button>
                  }
                  title="¿Restablecer el segundo factor?"
                  description="Se elimina su app autenticadora y sus códigos de recuperación; deberá configurarla de nuevo."
                  confirmLabel="Restablecer"
                  destructive
                  onConfirm={() => resetMfa.mutate(path)}
                />
              ) : null}
              {can(Perm.USER_REVOKE_SESSIONS) ? (
                <Button variant="outline" size="sm" onClick={() => revoke.mutate(path)}>
                  Cerrar todas sus sesiones
                </Button>
              ) : null}
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm">2FA: {u.mfa_enabled ? "configurado" : "sin configurar"}</p>
            <UserSessions userId={userId} />
          </CardContent>
        </Card>
      </div>
    </section>
  );
}

function NameCard({ user }: { user: UserOut }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(user.full_name);
  const update = useMutation({
    ...updateUserMutation(),
    onSuccess: (data) => {
      queryClient.setQueryData(getUserQueryKey({ path: { user_id: user.id } }), data);
      toast.success("Nombre actualizado.");
    },
  });
  return (
    <Card>
      <CardContent>
        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            update.mutate({ path: { user_id: user.id }, body: { full_name: name.trim() } });
          }}
        >
          <div className="grid flex-1 gap-1.5">
            <Label htmlFor="user-name">Nombre completo</Label>
            <Input
              id="user-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              minLength={2}
              required
            />
          </div>
          <Button
            type="submit"
            variant="outline"
            disabled={name.trim() === user.full_name || update.isPending}
          >
            Guardar
          </Button>
        </form>
        <ProblemAlert error={update.error} />
      </CardContent>
    </Card>
  );
}

function RolesCard({ user, editable }: { user: UserOut; editable: boolean }) {
  const queryClient = useQueryClient();
  const roles = useQuery(listRolesOptions());
  const [selected, setSelected] = useState<string[]>(user.roles.map((r) => r.id));
  useEffect(() => setSelected(user.roles.map((r) => r.id)), [user.roles]);
  const save = useMutation({
    ...setUserRolesMutation(),
    onSuccess: (data) => {
      queryClient.setQueryData(getUserQueryKey({ path: { user_id: user.id } }), data);
      toast.success("Roles actualizados.");
    },
  });
  const changed =
    [...selected].sort().join() !==
    user.roles
      .map((r) => r.id)
      .sort()
      .join();
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Roles</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <ProblemAlert error={save.error} />
        <div className="grid gap-2 sm:grid-cols-2">
          {(roles.data ?? []).map((role) => (
            <LabeledToggle
              key={role.id}
              disabled={!editable}
              checked={selected.includes(role.id)}
              onCheckedChange={(c) =>
                setSelected(c ? [...selected, role.id] : selected.filter((id) => id !== role.id))
              }
            >
              <span>
                {role.name}
                {role.description ? (
                  <span className="block text-xs text-muted-foreground">{role.description}</span>
                ) : null}
              </span>
            </LabeledToggle>
          ))}
        </div>
        {editable ? (
          <Button
            variant="outline"
            size="sm"
            disabled={!changed || save.isPending}
            onClick={() =>
              save.mutate({ path: { user_id: user.id }, body: { role_ids: selected } })
            }
          >
            Guardar roles
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

function UserSessions({ userId }: { userId: string }) {
  const sessions = useQuery(listUserSessionsOptions({ path: { user_id: userId } }));
  if (sessions.isError) return <ProblemAlert error={sessions.error} />;
  return <SessionsTable sessions={sessions.data ?? []} />;
}
