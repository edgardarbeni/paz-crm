import { createFormHook, createFormHookContexts } from "@tanstack/react-form";
import { useId } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

export const { fieldContext, formContext, useFieldContext, useFormContext } =
  createFormHookContexts();

/** Validation messages from Standard Schema issues (Zod) or plain strings. */
export function errorText(errors: unknown[]): string | undefined {
  const messages = errors
    .map((error) =>
      typeof error === "string"
        ? error
        : typeof error === "object" && error !== null && "message" in error
          ? String((error as { message: unknown }).message)
          : null,
    )
    .filter(Boolean);
  return messages.length ? [...new Set(messages)].join(" · ") : undefined;
}

interface FieldShellProps {
  id: string;
  label: string;
  description?: string;
  error?: string;
  required?: boolean;
  children: React.ReactNode;
  className?: string;
}

export function FieldShell({
  id,
  label,
  description,
  error,
  required,
  children,
  className,
}: FieldShellProps) {
  return (
    <div className={cn("grid gap-1.5", className)}>
      <Label htmlFor={id}>
        {label}
        {required ? (
          <span aria-hidden="true" className="text-destructive">
            {" "}
            *
          </span>
        ) : null}
      </Label>
      {children}
      {description && !error ? (
        <p id={`${id}-description`} className="text-xs text-muted-foreground">
          {description}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-xs text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function useFieldA11y(description?: string) {
  const field = useFieldContext<unknown>();
  const id = useId();
  const error = field.state.meta.isTouched ? errorText(field.state.meta.errors) : undefined;
  const describedBy = error ? `${id}-error` : description ? `${id}-description` : undefined;
  return { field, id, error, describedBy };
}

interface TextFieldProps
  extends Omit<React.ComponentProps<"input">, "value" | "onChange" | "name" | "id"> {
  label: string;
  description?: string;
  /** Transform each keystroke (e.g. uppercase CURP). */
  normalize?: (value: string) => string;
}

function TextField({
  label,
  description,
  normalize,
  required,
  className,
  ...props
}: TextFieldProps) {
  const { field, id, error, describedBy } = useFieldA11y(description);
  return (
    <FieldShell
      id={id}
      label={label}
      description={description}
      error={error}
      required={required}
      className={className}
    >
      <Input
        id={id}
        name={field.name}
        value={(field.state.value as string | null | undefined) ?? ""}
        onBlur={field.handleBlur}
        onChange={(event) =>
          field.handleChange(normalize ? normalize(event.target.value) : event.target.value)
        }
        aria-invalid={!!error}
        aria-describedby={describedBy}
        aria-required={required}
        {...props}
      />
    </FieldShell>
  );
}

function NumberField({ label, description, required, className, ...props }: TextFieldProps) {
  const { field, id, error, describedBy } = useFieldA11y(description);
  const value = field.state.value as number | null | undefined;
  return (
    <FieldShell
      id={id}
      label={label}
      description={description}
      error={error}
      required={required}
      className={className}
    >
      <Input
        id={id}
        name={field.name}
        type="number"
        inputMode="numeric"
        value={value ?? ""}
        onBlur={field.handleBlur}
        onChange={(event) =>
          field.handleChange(event.target.value === "" ? null : Number(event.target.value))
        }
        aria-invalid={!!error}
        aria-describedby={describedBy}
        {...props}
      />
    </FieldShell>
  );
}

function TextareaField({
  label,
  description,
  required,
  className,
  ...props
}: Omit<React.ComponentProps<"textarea">, "value" | "onChange" | "name" | "id"> & {
  label: string;
  description?: string;
}) {
  const { field, id, error, describedBy } = useFieldA11y(description);
  return (
    <FieldShell
      id={id}
      label={label}
      description={description}
      error={error}
      required={required}
      className={className}
    >
      <Textarea
        id={id}
        name={field.name}
        value={(field.state.value as string | null | undefined) ?? ""}
        onBlur={field.handleBlur}
        onChange={(event) => field.handleChange(event.target.value)}
        aria-invalid={!!error}
        aria-describedby={describedBy}
        {...props}
      />
    </FieldShell>
  );
}

export interface Option {
  value: string;
  label: string;
}

/** Native select: fastest with the keyboard (type-ahead) and fully accessible. */
function SelectField({
  label,
  options,
  description,
  required,
  placeholder = "Selecciona…",
  className,
  disabled,
}: {
  label: string;
  options: Option[];
  description?: string;
  required?: boolean;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}) {
  const { field, id, error, describedBy } = useFieldA11y(description);
  return (
    <FieldShell
      id={id}
      label={label}
      description={description}
      error={error}
      required={required}
      className={className}
    >
      <select
        id={id}
        name={field.name}
        value={(field.state.value as string | null | undefined) ?? ""}
        onBlur={field.handleBlur}
        onChange={(event) =>
          field.handleChange(event.target.value === "" ? null : event.target.value)
        }
        aria-invalid={!!error}
        aria-describedby={describedBy}
        disabled={disabled}
        className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 aria-invalid:border-destructive disabled:opacity-50"
      >
        <option value="">{placeholder}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </FieldShell>
  );
}

function CheckboxField({ label, description }: { label: string; description?: string }) {
  const { field, id } = useFieldA11y(description);
  return (
    <div className="flex items-start gap-2">
      <Checkbox
        id={id}
        checked={!!field.state.value}
        onCheckedChange={(checked) => field.handleChange(checked === true)}
        onBlur={field.handleBlur}
      />
      <div className="grid gap-0.5">
        <Label htmlFor={id}>{label}</Label>
        {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
      </div>
    </div>
  );
}

function SubmitButton({ children, className }: { children: React.ReactNode; className?: string }) {
  const form = useFormContext();
  return (
    <form.Subscribe selector={(state) => [state.canSubmit, state.isSubmitting] as const}>
      {([canSubmit, isSubmitting]) => (
        <Button type="submit" disabled={!canSubmit || isSubmitting} className={className}>
          {isSubmitting ? "Guardando…" : children}
        </Button>
      )}
    </form.Subscribe>
  );
}

export const { useAppForm, withForm } = createFormHook({
  fieldContext,
  formContext,
  fieldComponents: { TextField, NumberField, TextareaField, SelectField, CheckboxField },
  formComponents: { SubmitButton },
});

/** Submit on Ctrl/⌘+Enter from any field of the form. */
export function submitOnModEnter(event: React.KeyboardEvent<HTMLFormElement>) {
  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
    event.preventDefault();
    event.currentTarget.requestSubmit();
  }
}
