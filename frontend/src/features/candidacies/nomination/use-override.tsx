import { useState } from "react";
import type { Override } from "@/client/types.gen";
import { FormDialog } from "@/components/form-dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { isProblem, type RuleViolation } from "@/lib/api";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";

type Pending = { violations: RuleViolation[]; retry: (override: Override) => Promise<unknown> };

/**
 * Blocking rule violations (409 rule-violation, D-67): users with `candidacies.rule.override`
 * get a dialog to accept them with a reason and retry; everyone else sees the error.
 */
export function useOverride() {
  const can = useCan();
  const [pending, setPending] = useState<Pending | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  /** Runs `action`; if it is blocked by rules and the user may override, asks and retries. */
  async function run<T>(action: (override?: Override) => Promise<T>): Promise<T | undefined> {
    try {
      return await action();
    } catch (error) {
      if (
        isProblem(error) &&
        error.code === "rule-violation" &&
        error.violations?.length &&
        can(Perm.RULE_OVERRIDE)
      ) {
        setReason("");
        setPending({ violations: error.violations, retry: action });
        return undefined;
      }
      throw error;
    }
  }

  const dialog = pending ? (
    <FormDialog
      open
      onOpenChange={(open) => !open && setPending(null)}
      title="La operación viola reglas bloqueantes"
      description="Puedes aceptar la excepción con un motivo; quedará registrada con tu nombre."
    >
      <form
        className="grid gap-4"
        onSubmit={async (event) => {
          event.preventDefault();
          setBusy(true);
          try {
            await pending.retry({
              rules: [...new Set(pending.violations.map((v) => v.rule))],
              reason: reason.trim(),
            });
            setPending(null);
          } finally {
            setBusy(false);
          }
        }}
      >
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {pending.violations.map((v) => (
            <li key={`${v.rule}-${v.formula_id ?? "n"}`}>{v.message}</li>
          ))}
        </ul>
        <div className="grid gap-1.5">
          <Label htmlFor="override-reason">Motivo de la excepción</Label>
          <Textarea
            id="override-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            autoFocus
            minLength={5}
            required
          />
        </div>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => setPending(null)}>
            Cancelar
          </Button>
          <Button type="submit" disabled={busy || reason.trim().length < 5}>
            Aceptar excepción
          </Button>
        </div>
      </form>
    </FormDialog>
  ) : null;

  return { run, dialog };
}
