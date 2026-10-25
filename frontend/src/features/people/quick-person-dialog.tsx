import { useMutation } from "@tanstack/react-query";
import { createPersonMutation } from "@/client/@tanstack/react-query.gen";
import type { PersonCreate } from "@/client/types.gen";
import type { ComboItem } from "@/components/async-combobox";
import { submitOnModEnter, useAppForm } from "@/components/form/form";
import { FormDialog } from "@/components/form-dialog";
import { ProblemAlert } from "@/components/problem-alert";
import { normalizeCurp, parseCurp } from "@/features/people/curp";
import { blanksToNull } from "@/lib/forms";
import { options, SEX_LABELS } from "@/lib/labels";

/** Minimal person capture from the nomination editor: name, sex and (optional) CURP. */
export function QuickPersonDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (item: ComboItem) => void;
}) {
  const create = useMutation(createPersonMutation());
  const form = useAppForm({
    defaultValues: {
      given_names: "",
      paternal_surname: "",
      maternal_surname: "",
      sex: "",
      curp: "",
    },
    onSubmit: async ({ value }) => {
      const body = blanksToNull(value) as PersonCreate;
      const person = await create.mutateAsync({ body }).catch(() => null);
      if (person) {
        onCreated({ id: person.id, label: person.full_name, hint: person.curp ?? undefined });
        form.reset();
        onClose();
      }
    },
  });
  return (
    <FormDialog open={open} onOpenChange={(o) => !o && onClose()} title="Nueva persona">
      <form
        className="grid gap-3"
        noValidate
        onKeyDown={submitOnModEnter}
        onSubmit={(event) => {
          event.preventDefault();
          event.stopPropagation();
          form.handleSubmit();
        }}
      >
        <ProblemAlert error={create.error} />
        <form.AppField
          name="given_names"
          validators={{ onBlur: ({ value }) => (value.trim() ? undefined : "Obligatorio.") }}
        >
          {(field) => <field.TextField label="Nombre(s)" autoFocus required />}
        </form.AppField>
        <div className="grid grid-cols-2 gap-3">
          <form.AppField
            name="paternal_surname"
            validators={{ onBlur: ({ value }) => (value.trim() ? undefined : "Obligatorio.") }}
          >
            {(field) => <field.TextField label="Primer apellido" required />}
          </form.AppField>
          <form.AppField name="maternal_surname">
            {(field) => <field.TextField label="Segundo apellido" />}
          </form.AppField>
        </div>
        <div className="grid grid-cols-[1fr_2fr] gap-3">
          <form.AppField name="sex">
            {(field) => <field.SelectField label="Sexo" options={options(SEX_LABELS)} />}
          </form.AppField>
          <form.AppField
            name="curp"
            validators={{
              onChange: ({ value }) => {
                const curp = normalizeCurp(value);
                if (!curp) return undefined;
                if (curp.length < 18) return undefined; // still typing
                const result = parseCurp(curp);
                return result.ok ? undefined : result.error;
              },
              onBlur: ({ value }) => {
                const curp = normalizeCurp(value);
                if (!curp) return undefined;
                const result = parseCurp(curp);
                return result.ok ? undefined : result.error;
              },
            }}
          >
            {(field) => (
              <field.TextField
                label="CURP"
                maxLength={18}
                normalize={normalizeCurp}
                description="Opcional; si se captura, el sexo se toma de ella."
              />
            )}
          </form.AppField>
        </div>
        <form.AppForm>
          <form.SubmitButton>Guardar persona</form.SubmitButton>
        </form.AppForm>
      </form>
    </FormDialog>
  );
}
