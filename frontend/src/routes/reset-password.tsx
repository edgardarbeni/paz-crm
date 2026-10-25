import { useMutation } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { z } from "zod";
import { resetPasswordMutation } from "@/client/@tanstack/react-query.gen";
import { useAppForm } from "@/components/form/form";
import { ProblemAlert } from "@/components/problem-alert";
import { AuthCard } from "@/features/auth/auth-card";
import { newPassword } from "@/features/auth/password-field-rules";

export const Route = createFileRoute("/reset-password")({
  validateSearch: z.object({ token: z.string().catch("") }),
  component: ResetPasswordPage,
});

function ResetPasswordPage() {
  const { token } = Route.useSearch();
  const reset = useMutation(resetPasswordMutation());
  const form = useAppForm({
    defaultValues: { password: "", confirm: "" },
    validators: { onSubmit: newPassword },
    onSubmit: async ({ value }) => {
      await reset.mutateAsync({ body: { token, new_password: value.password } }).catch(() => {});
    },
  });
  if (reset.isSuccess) {
    return (
      <AuthCard title="Contraseña actualizada">
        <p className="text-sm">Ya puedes iniciar sesión con tu nueva contraseña.</p>
        <Link to="/login" className="mt-4 inline-block text-sm underline">
          Iniciar sesión
        </Link>
      </AuthCard>
    );
  }
  return (
    <AuthCard title="Nueva contraseña">
      {!token ? (
        <p className="text-sm text-destructive">El enlace no es válido. Solicita uno nuevo.</p>
      ) : (
        <form
          className="grid gap-4"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            form.handleSubmit();
          }}
        >
          <ProblemAlert error={reset.error} />
          <form.AppField name="password">
            {(field) => (
              <field.TextField
                label="Nueva contraseña"
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
            <form.SubmitButton className="h-10">Guardar</form.SubmitButton>
          </form.AppForm>
        </form>
      )}
    </AuthCard>
  );
}
