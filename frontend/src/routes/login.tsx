import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { z } from "zod";
import { loginMutation, verifyMfaMutation } from "@/client/@tanstack/react-query.gen";
import type { AuthenticatedResponse, LoginResponse } from "@/client/types.gen";
import { zLoginRequest } from "@/client/zod.gen";
import { submitOnModEnter, useAppForm } from "@/components/form/form";
import { ProblemAlert } from "@/components/problem-alert";
import { Button } from "@/components/ui/button";
import { AuthCard } from "@/features/auth/auth-card";
import { safeRedirect, startSession } from "@/features/auth/complete-login";

export const Route = createFileRoute("/login")({
  validateSearch: z.object({ redirect: z.string().optional() }),
  component: LoginPage,
});

function LoginPage() {
  const { redirect } = Route.useSearch();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [mfaToken, setMfaToken] = useState<string | null>(null);

  function finish(result: AuthenticatedResponse) {
    startSession(queryClient, result.access_token, result.scope);
    if (result.scope === "mfa_enrollment") {
      navigate({ to: "/enroll-mfa" });
    } else {
      navigate({ href: safeRedirect(redirect) });
    }
  }

  return mfaToken ? (
    <MfaStep mfaToken={mfaToken} onDone={finish} onBack={() => setMfaToken(null)} />
  ) : (
    <CredentialsStep
      onDone={(result) =>
        result.status === "mfa_required" ? setMfaToken(result.mfa_token) : finish(result)
      }
    />
  );
}

function CredentialsStep({ onDone }: { onDone: (result: LoginResponse) => void }) {
  const login = useMutation({ ...loginMutation(), onSuccess: (data) => onDone(data) });
  const form = useAppForm({
    defaultValues: { email: "", password: "" },
    validators: { onSubmit: zLoginRequest },
    onSubmit: async ({ value }) => {
      await login
        .mutateAsync({ body: { ...value, device_label: navigator.userAgent.slice(0, 200) } })
        .catch(() => {});
    },
  });
  return (
    <AuthCard title="Iniciar sesión" description="Panel de administración de PAZOS.">
      <form
        className="grid gap-4"
        noValidate
        onKeyDown={submitOnModEnter}
        onSubmit={(event) => {
          event.preventDefault();
          form.handleSubmit();
        }}
      >
        <ProblemAlert error={login.error} title="No fue posible iniciar sesión" />
        <form.AppField name="email">
          {(field) => (
            <field.TextField
              label="Correo"
              type="email"
              autoComplete="username"
              autoFocus
              required
            />
          )}
        </form.AppField>
        <form.AppField name="password">
          {(field) => (
            <field.TextField
              label="Contraseña"
              type="password"
              autoComplete="current-password"
              required
            />
          )}
        </form.AppField>
        <form.AppForm>
          <form.SubmitButton>Entrar</form.SubmitButton>
        </form.AppForm>
        <Link
          to="/forgot-password"
          className="text-center text-sm text-muted-foreground underline-offset-4 hover:underline"
        >
          ¿Olvidaste tu contraseña?
        </Link>
      </form>
    </AuthCard>
  );
}

function MfaStep({
  mfaToken,
  onDone,
  onBack,
}: {
  mfaToken: string;
  onDone: (result: AuthenticatedResponse) => void;
  onBack: () => void;
}) {
  const [useRecovery, setUseRecovery] = useState(false);
  const verify = useMutation({ ...verifyMfaMutation(), onSuccess: onDone });
  const form = useAppForm({
    defaultValues: { code: "" },
    validators: {
      onSubmit: useRecovery
        ? z.object({ code: z.string().min(8, "Escribe tu código de recuperación.") })
        : z.object({ code: z.string().regex(/^\d{6}$/, "El código tiene 6 dígitos.") }),
    },
    onSubmit: async ({ value }) => {
      const body = useRecovery
        ? { mfa_token: mfaToken, recovery_code: value.code.trim() }
        : { mfa_token: mfaToken, code: value.code };
      await verify.mutateAsync({ body }).catch(() => {});
    },
  });
  return (
    <AuthCard
      title="Segundo factor"
      description={
        useRecovery
          ? "Escribe uno de tus códigos de recuperación (cada uno sirve una sola vez)."
          : "Escribe el código de 6 dígitos de tu app autenticadora."
      }
    >
      <form
        className="grid gap-4"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          form.handleSubmit();
        }}
      >
        <ProblemAlert error={verify.error} title="Código no válido" />
        <form.AppField name="code">
          {(field) => (
            <field.TextField
              key={useRecovery ? "recovery" : "totp"}
              label={useRecovery ? "Código de recuperación" : "Código"}
              inputMode={useRecovery ? "text" : "numeric"}
              autoComplete="one-time-code"
              autoFocus
              required
              maxLength={useRecovery ? 32 : 6}
            />
          )}
        </form.AppField>
        <form.AppForm>
          <form.SubmitButton>Verificar</form.SubmitButton>
        </form.AppForm>
        <div className="flex justify-between text-sm">
          <Button type="button" variant="link" className="px-0" onClick={onBack}>
            Volver
          </Button>
          <Button
            type="button"
            variant="link"
            className="px-0"
            onClick={() => {
              setUseRecovery(!useRecovery);
              form.reset();
            }}
          >
            {useRecovery ? "Usar la app autenticadora" : "Usar un código de recuperación"}
          </Button>
        </div>
      </form>
    </AuthCard>
  );
}
