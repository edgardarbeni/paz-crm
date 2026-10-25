import { useMutation } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { forgotPasswordMutation } from "@/client/@tanstack/react-query.gen";
import { zPasswordForgotRequest } from "@/client/zod.gen";
import { useAppForm } from "@/components/form/form";
import { ProblemAlert } from "@/components/problem-alert";
import { AuthCard } from "@/features/auth/auth-card";

export const Route = createFileRoute("/forgot-password")({ component: ForgotPasswordPage });

function ForgotPasswordPage() {
  const forgot = useMutation(forgotPasswordMutation());
  const form = useAppForm({
    defaultValues: { email: "" },
    validators: { onSubmit: zPasswordForgotRequest },
    onSubmit: async ({ value }) => {
      await forgot.mutateAsync({ body: value }).catch(() => {});
    },
  });
  if (forgot.isSuccess) {
    return (
      <AuthCard title="Revisa tu correo">
        <p className="text-sm">
          Si el correo está registrado, te enviamos un enlace para restablecer tu contraseña. El
          enlace vence pronto y sirve una sola vez.
        </p>
        <Link to="/login" className="mt-4 inline-block text-sm underline">
          Volver a iniciar sesión
        </Link>
      </AuthCard>
    );
  }
  return (
    <AuthCard title="Recuperar contraseña" description="Te enviaremos un enlace a tu correo.">
      <form
        className="grid gap-4"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          form.handleSubmit();
        }}
      >
        <ProblemAlert error={forgot.error} />
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
        <form.AppForm>
          <form.SubmitButton className="h-10">Enviar enlace</form.SubmitButton>
        </form.AppForm>
        <Link to="/login" className="text-center text-sm text-muted-foreground hover:underline">
          Volver
        </Link>
      </form>
    </AuthCard>
  );
}
