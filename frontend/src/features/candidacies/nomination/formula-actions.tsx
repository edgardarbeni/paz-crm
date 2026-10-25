import { MoreHorizontal } from "lucide-react";
import { useState } from "react";
import { changeFormulaStatus, substituteFormula } from "@/client/sdk.gen";
import type { FormulaOut, NominationOut } from "@/client/types.gen";
import { FormDialog } from "@/components/form-dialog";
import { ProblemAlert } from "@/components/problem-alert";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { CaptureRow } from "@/features/candidacies/nomination/capture-row";
import type { useOverride } from "@/features/candidacies/nomination/use-override";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";

type Dialog = "substitute" | "cancel" | null;

/** Status transitions and substitution for one formula (D-29, D-68). */
export function FormulaActions({
  formula,
  hasSubstitute,
  editable,
  draft,
  onEdit,
  onChanged,
  override,
}: {
  formula: FormulaOut;
  hasSubstitute: boolean;
  editable: boolean;
  draft: boolean;
  onEdit: () => void;
  onChanged: (nomination: NominationOut) => void;
  override: ReturnType<typeof useOverride>;
}) {
  const can = useCan();
  const [dialog, setDialog] = useState<Dialog>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>(null);
  if (!editable) return null;
  const write = can(Perm.NOMINATION_WRITE);
  const approve = can(Perm.NOMINATION_APPROVE);
  const label = `posición ${formula.position}`;

  async function setStatus(to: "registered" | "approved" | "cancelled", why?: string) {
    setError(null);
    try {
      const { data } = await changeFormulaStatus({
        path: { formula_id: formula.id },
        body: { to_status: to, reason: why || null },
        throwOnError: true,
      });
      onChanged(data);
      setDialog(null);
    } catch (e) {
      setError(e);
    }
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label={`Acciones de la ${label}`}>
            <MoreHorizontal aria-hidden />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {draft && formula.status === "aspirant" && write ? (
            <DropdownMenuItem onSelect={onEdit}>Cambiar integrantes</DropdownMenuItem>
          ) : null}
          {formula.status === "aspirant" && write ? (
            <DropdownMenuItem onSelect={() => setStatus("registered")}>
              Marcar como registrada
            </DropdownMenuItem>
          ) : null}
          {formula.status === "registered" && approve ? (
            <DropdownMenuItem onSelect={() => setStatus("approved")}>Aprobar</DropdownMenuItem>
          ) : null}
          {approve ? (
            <DropdownMenuItem onSelect={() => setDialog("substitute")}>Sustituir…</DropdownMenuItem>
          ) : null}
          {(formula.status === "aspirant" && write) || approve ? (
            <DropdownMenuItem variant="destructive" onSelect={() => setDialog("cancel")}>
              Cancelar fórmula…
            </DropdownMenuItem>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>
      {error && !dialog ? (
        <div className="col-span-full">
          <ProblemAlert error={error} />
        </div>
      ) : null}
      {dialog === "cancel" ? (
        <FormDialog
          open
          onOpenChange={(o) => !o && setDialog(null)}
          title={`Cancelar la fórmula de la ${label}`}
        >
          <form
            className="grid gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              setStatus("cancelled", reason.trim());
            }}
          >
            <ProblemAlert error={error} />
            <Label htmlFor="cancel-reason">Motivo</Label>
            <Textarea
              id="cancel-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              autoFocus
              required
              minLength={5}
            />
            <Button type="submit" variant="destructive" disabled={reason.trim().length < 5}>
              Cancelar fórmula
            </Button>
          </form>
        </FormDialog>
      ) : null}
      {dialog === "substitute" ? (
        <FormDialog
          open
          onOpenChange={(o) => !o && setDialog(null)}
          title={`Sustituir la fórmula de la ${label}`}
          description="Se crea una fórmula nueva en la misma posición; la actual queda en el historial como sustituida."
          wide
        >
          <div className="grid gap-3">
            <ProblemAlert error={error} />
            <div className="grid gap-1.5">
              <Label htmlFor="substitution-reason">Motivo de la sustitución</Label>
              <Textarea
                id="substitution-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                autoFocus
                minLength={5}
                placeholder="Renuncia, inelegibilidad, acuerdo del órgano electoral…"
              />
            </div>
            <CaptureRow
              rowId={`substitute-${formula.id}`}
              label={label}
              hasSubstitute={hasSubstitute}
              saveLabel="Sustituir"
              initial={{
                owner: formula.owner
                  ? { id: formula.owner.person_id, label: formula.owner.full_name }
                  : null,
                substitute: formula.substitute
                  ? { id: formula.substitute.person_id, label: formula.substitute.full_name }
                  : null,
              }}
              onSave={async (value) => {
                if (reason.trim().length < 5) {
                  setError(new Error("Escribe el motivo de la sustitución."));
                  return;
                }
                setError(null);
                try {
                  const result = await override.run(async (ov) => {
                    const { data } = await substituteFormula({
                      path: { formula_id: formula.id },
                      body: {
                        owner_person_id:
                          value.owner?.id !== formula.owner?.person_id ? value.owner?.id : null,
                        substitute_person_id:
                          value.substitute?.id !== formula.substitute?.person_id
                            ? value.substitute?.id
                            : null,
                        reason: reason.trim(),
                        override: ov,
                      },
                      throwOnError: true,
                    });
                    onChanged(data);
                    setDialog(null);
                    return data;
                  });
                  return result;
                } catch (e) {
                  setError(e);
                }
              }}
            />
          </div>
        </FormDialog>
      ) : null}
    </>
  );
}
