import { useMutation, useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { z } from "zod";
import { acceptInvitationMutation } from "@/client/@tanstack/react-query.gen";
import { inspectInvitation } from "@/client/sdk.gen";
import type { InvitationInfo } from "@/client/types.gen";
import { useAppForm } from "@/components/form/form";
import { ProblemAlert } from "@/components/problem-alert";
import { AuthCard } from "@/features/auth/auth-card";
import { newPassword } from "@/features/auth/password-field-rules";

export const Route = createFileRoute("/accept-invitation")({
  validateSearch: z.object({ token: z.string().catch("") }),
  component: AcceptInvitationPage,
});

function AcceptInvitationPage() {
  const { token } = Route.useSearch();
  const info = useQuery({
    queryKey: ["invitation", token],
    queryFn: async () => (await inspectInvitation({ body: { token }, throwOnError: true })).data,
    enabled: !!token,
    retry: false,
  });
  if (!token || info.isError) {
    return (
      <AuthCard title="Activar tu cuenta">
        <ProblemAlert
          error={info.error ?? new Error("Enlace no válido")}
          title="Invitación no válida"
        />
      </AuthCard>
    );
  }
  if (!info.data) {
    return <AuthCard title="Activar tu cuenta">Cargando invitación…</AuthCard>;
  }
  return <InvitationForm token={token} info={info.data} />;
}

function InvitationForm({ token, info }: { token: string; info: InvitationInfo }) {
  const accept = useMutation(acceptInvitationMutation());
  const form = useAppForm({
    defaultValues: { full_name: info.full_name, password: "", confirm: "" },
    validators: {
      onSubmit: newPassword.and(z.object({ full_name: z.string().min(2, "Escribe tu nombre.") })),
    },
    onSubmit: async ({ value }) => {
      await accept
        .mutateAsync({ body: { token, password: value.password, full_name: value.full_name } })
        .catch(() => {});
    },
  });
  if (accept.isSuccess) {
    return (
      <AuthCard title="Cuenta activada">
        <p className="text-sm">
          Inicia sesión con tu correo y contraseña. Si tu rol lo exige, configurarás tu app
          autenticadora al entrar.
        </p>
        <Link to="/login" className="mt-4 inline-block text-sm underline">
          Iniciar sesión
        </Link>
      </AuthCard>
    );
  }
  return (
    <AuthCard title="Activar tu cuenta" description={`Invitación para ${info.email}.`}>
      <form
        className="grid gap-4"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          form.handleSubmit();
        }}
      >
        <ProblemAlert error={accept.error} />
        <form.AppField name="full_name">
          {(field) => <field.TextField label="Nombre completo" autoComplete="name" required />}
        </form.AppField>
        <form.AppField name="password">
          {(field) => (
            <field.TextField
              label="Contraseña"
              type="password"
              autoComplete="new-password"
              autoFocus
              required
            />
          )}
        </form.AppField>
        <form.AppField name="confirm">
          {(field) => (
            <field.TextField
              label="Confirmar"
              type="password"
              autoComplete="new-password"
              required
            />
          )}
        </form.AppField>
        <form.AppForm>
          <form.SubmitButton className="h-10">Activar cuenta</form.SubmitButton>
        </form.AppForm>
      </form>
    </AuthCard>
  );
}
