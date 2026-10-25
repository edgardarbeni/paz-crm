import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import {
  changePasswordMutation,
  listMySessionsOptions,
  listMySessionsQueryKey,
  regenerateRecoveryCodesMutation,
  revokeMyOtherSessionsMutation,
  revokeMySessionMutation,
} from "@/client/@tanstack/react-query.gen";
import { useAppForm } from "@/components/form/form";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RecoveryCodes } from "@/features/auth/recovery-codes";
import { SessionsTable } from "@/features/identity/sessions-table";
import { useMe } from "@/lib/auth/use-me";

export const Route = createFileRoute("/_app/account")({ component: AccountPage });

function AccountPage() {
  const me = useMe();
  return (
    <section className="max-w-3xl">
      <PageHeader
        title="Mi cuenta"
        description={me ? `${me.full_name} · ${me.email}` : undefined}
      />
      <div className="space-y-6">
        <ChangePassword />
        <RecoveryCodesCard enabled={!!me?.mfa.enabled} />
        <MySessions />
      </div>
    </section>
  );
}

function ChangePassword() {
  const change = useMutation({
    ...changePasswordMutation(),
    onSuccess: () => toast.success("Contraseña actualizada; tus otras sesiones se cerraron."),
  });
  const form = useAppForm({
    defaultValues: { current_password: "", password: "", confirm: "" },
    validators: {
      onSubmit: z
        .object({
          current_password: z.string().min(1, "Obligatoria."),
          password: z.string().min(12, "Usa al menos 12 caracteres."),
          confirm: z.string(),
        })
        .refine((v) => v.password === v.confirm, {
          message: "Las contraseñas no coinciden.",
          path: ["confirm"],
        }),
    },
    onSubmit: async ({ value }) => {
      await change
        .mutateAsync({
          body: { current_password: value.current_password, new_password: value.password },
        })
        .then(() => form.reset())
        .catch(() => {});
    },
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Cambiar contraseña</h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form
          className="grid gap-3 sm:grid-cols-3"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            form.handleSubmit();
          }}
        >
          <div className="sm:col-span-3">
            <ProblemAlert error={change.error} />
          </div>
          <form.AppField name="current_password">
            {(f) => <f.TextField label="Actual" type="password" autoComplete="current-password" />}
          </form.AppField>
          <form.AppField name="password">
            {(f) => <f.TextField label="Nueva" type="password" autoComplete="new-password" />}
          </form.AppField>
          <form.AppField name="confirm">
            {(f) => <f.TextField label="Confirmar" type="password" autoComplete="new-password" />}
          </form.AppField>
          <form.AppForm>
            <form.SubmitButton className="justify-self-start">Cambiar contraseña</form.SubmitButton>
          </form.AppForm>
        </form>
      </CardContent>
    </Card>
  );
}

function RecoveryCodesCard({ enabled }: { enabled: boolean }) {
  const [code, setCode] = useState("");
  const regenerate = useMutation({
    ...regenerateRecoveryCodesMutation(),
    onSuccess: () => setCode(""),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Segundo factor</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {!enabled ? (
          <p className="text-sm text-muted-foreground">
            Tu cuenta no tiene app autenticadora configurada.
          </p>
        ) : regenerate.data ? (
          <RecoveryCodes codes={regenerate.data.recovery_codes} />
        ) : (
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              regenerate.mutate({ body: { code } });
            }}
          >
            <p className="w-full text-sm">
              Genera códigos de recuperación nuevos; los anteriores dejan de servir.
            </p>
            <ProblemAlert error={regenerate.error} />
            <div className="grid gap-1.5">
              <Label htmlFor="mfa-code">Código de tu app</Label>
              <Input
                id="mfa-code"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                className="w-32"
              />
            </div>
            <Button
              type="submit"
              variant="outline"
              disabled={code.length !== 6 || regenerate.isPending}
            >
              Regenerar códigos
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

function MySessions() {
  const queryClient = useQueryClient();
  const sessions = useQuery(listMySessionsOptions());
  const refresh = () => queryClient.invalidateQueries({ queryKey: listMySessionsQueryKey() });
  const revoke = useMutation({ ...revokeMySessionMutation(), onSuccess: refresh });
  const revokeOthers = useMutation({
    ...revokeMyOtherSessionsMutation(),
    onSuccess: () => {
      refresh();
      toast.success("Se cerraron tus otras sesiones.");
    },
  });
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>
          <h2>Sesiones activas</h2>
        </CardTitle>
        <Button variant="outline" size="sm" onClick={() => revokeOthers.mutate({})}>
          Cerrar las demás
        </Button>
      </CardHeader>
      <CardContent>
        <ProblemAlert error={sessions.error ?? revoke.error ?? revokeOthers.error} />
        <SessionsTable
          sessions={sessions.data ?? []}
          onRevoke={(s) => revoke.mutate({ path: { session_id: s.id } })}
        />
      </CardContent>
    </Card>
  );
}
