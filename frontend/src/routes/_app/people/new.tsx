import { useMutation } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { createPersonMutation } from "@/client/@tanstack/react-query.gen";
import type { PersonCreate } from "@/client/types.gen";
import { PageHeader } from "@/components/page-header";
import { PersonForm } from "@/features/people/person-form";

export const Route = createFileRoute("/_app/people/new")({ component: NewPersonPage });

function NewPersonPage() {
  const navigate = useNavigate();
  const create = useMutation({
    ...createPersonMutation(),
    onSuccess: (person) => {
      toast.success("Persona registrada.");
      for (const warning of person.warnings ?? []) toast.warning(warning);
      navigate({ to: "/people/$personId", params: { personId: person.id } });
    },
  });
  return (
    <section className="max-w-4xl">
      <PageHeader title="Nueva persona" />
      <PersonForm
        error={create.error}
        onSubmit={(body) => create.mutateAsync({ body: body as PersonCreate })}
      />
    </section>
  );
}
