import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { z } from "zod";
import { confirmTotpMutation, setupTotpMutation } from "@/client/@tanstack/react-query.gen";
import { useAppForm } from "@/components/form/form";
import { ProblemAlert } from "@/components/problem-alert";
import { Button } from "@/components/ui/button";
import { AuthCard } from "@/features/auth/auth-card";
import { startSession } from "@/features/auth/complete-login";
import { RecoveryCodes } from "@/features/auth/recovery-codes";
import { getSession, refreshAccessToken } from "@/lib/auth/session";

export const Route = createFileRoute("/enroll-mfa")({
  beforeLoad: async ({ location }) => {
    if (!getSession().accessToken && !(await refreshAccessToken())) {
      throw redirect({ to: "/login", search: { redirect: location.href } });
    }
  },
  component: EnrollMfaPage,
});

/** TOTP enrollment (D-49): required on first login for roles with `requires_mfa`. */
function EnrollMfaPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const setup = useMutation(setupTotpMutation());
  const [result, setResult] = useState<{ token: string; codes: string[] } | null>(null);
  const confirm = useMutation({
    ...confirmTotpMutation(),
    onSuccess: (data) => setResult({ token: data.access_token, codes: data.recovery_codes }),
  });
  const form = useAppForm({
    defaultValues: { code: "" },
    validators: {
      onSubmit: z.object({ code: z.string().regex(/^\d{6}$/, "El código tiene 6 dígitos.") }),
    },
    onSubmit: async ({ value }) => {
      await confirm.mutateAsync({ body: { code: value.code } }).catch(() => {});
    },
  });
  const { mutate } = setup;
  const started = useRef(false);
  useEffect(() => {
    // Once: each setup call issues a new secret, so StrictMode's double effect must not repeat it.
    if (started.current) return;
    started.current = true;
    mutate({});
  }, [mutate]);

  if (result) {
    return (
      <AuthCard title="Segundo factor activado">
        <RecoveryCodes codes={result.codes} />
        <Button
          className="mt-4 w-full"
          onClick={() => {
            startSession(queryClient, result.token, "full");
            navigate({ to: "/" });
          }}
        >
          Ya los guardé, continuar
        </Button>
      </AuthCard>
    );
  }
  return (
    <AuthCard
      title="Configura tu app autenticadora"
      description="Escanea el código con Google Authenticator, Microsoft Authenticator o 1Password y escribe el código que muestre."
    >
      <div className="grid gap-4">
        <ProblemAlert error={setup.error} />
        {setup.data ? (
          <>
            <img
              src={setup.data.qr_svg}
              alt="Código QR para la app autenticadora"
              className="mx-auto size-48"
            />
            <div className="text-center text-xs text-muted-foreground">
              Captura manual:{" "}
              <code className="break-all font-mono text-foreground">{setup.data.secret}</code>
            </div>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">Generando clave…</p>
        )}
        <form
          className="grid gap-4"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            form.handleSubmit();
          }}
        >
          <ProblemAlert error={confirm.error} title="Código no válido" />
          <form.AppField name="code">
            {(field) => (
              <field.TextField
                label="Código"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                autoFocus
                required
              />
            )}
          </form.AppField>
          <form.AppForm>
            <form.SubmitButton>Activar</form.SubmitButton>
          </form.AppForm>
        </form>
      </div>
    </AuthCard>
  );
}
