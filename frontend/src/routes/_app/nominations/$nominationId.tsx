import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import {
  getNominationHistoryOptions,
  getNominationOptions,
  getNominationQueryKey,
  validateNominationOptions,
} from "@/client/@tanstack/react-query.gen";
import {
  approveNomination,
  cancelNomination,
  createFormula,
  submitNomination,
  updateFormulaMembers,
} from "@/client/sdk.gen";
import type { FormulaOut, NominationOut, SlotOut } from "@/client/types.gen";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { GeoName } from "@/features/candidacies/geo-name";
import { CaptureRow } from "@/features/candidacies/nomination/capture-row";
import { FormulaActions } from "@/features/candidacies/nomination/formula-actions";
import { useOverride } from "@/features/candidacies/nomination/use-override";
import { useCatalogs } from "@/features/candidacies/use-catalogs";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";
import { FORMULA_STATUS, formatDateTime, NOMINATION_STATUS, SEX_LABELS } from "@/lib/labels";

export const Route = createFileRoute("/_app/nominations/$nominationId")({
  component: NominationPage,
});

/** Focus the owner field of the next empty position (keyboard-first capture). */
function focusNextEmpty(after?: string) {
  requestAnimationFrame(() => {
    const rows = Array.from(document.querySelectorAll<HTMLElement>("[id^='capture-slot-']"));
    const index = after ? rows.findIndex((el) => el.id === `capture-${after}`) : -1;
    (rows[index + 1] ?? rows[0])?.focus();
  });
}

function NominationPage() {
  const { nominationId } = Route.useParams();
  const queryClient = useQueryClient();
  const can = useCan();
  const override = useOverride();
  const { officeById, partyById, processById } = useCatalogs();
  const key = getNominationQueryKey({ path: { nomination_id: nominationId } });
  const nomination = useQuery(getNominationOptions({ path: { nomination_id: nominationId } }));
  const [actionError, setActionError] = useState<unknown>(null);
  const [editing, setEditing] = useState<string | null>(null);

  function apply(data: NominationOut) {
    queryClient.setQueryData(key, data);
    queryClient.invalidateQueries({ queryKey: ["getNominationHistory"] });
    queryClient.invalidateQueries({ queryKey: ["validateNomination"] });
  }

  const action = useMutation({
    mutationFn: (kind: "submit" | "approve" | "cancel") =>
      override.run(async (ov) => {
        const options = {
          path: { nomination_id: nominationId },
          body: { override: ov },
          throwOnError: true as const,
        };
        const fn =
          kind === "submit"
            ? submitNomination
            : kind === "approve"
              ? approveNomination
              : cancelNomination;
        const { data } = await fn(options);
        apply(data);
        toast.success(
          kind === "submit"
            ? "Postulación enviada."
            : kind === "approve"
              ? "Postulación aprobada."
              : "Postulación cancelada.",
        );
        return data;
      }),
    onMutate: () => setActionError(null),
    onError: setActionError,
  });

  if (nomination.isError) return <ProblemAlert error={nomination.error} />;
  const n = nomination.data;
  if (!n) return <p className="text-muted-foreground">Cargando…</p>;
  const office = officeById.get(n.office_type_id);
  const draft = n.status === "draft";
  const editable = n.editable && n.status !== "cancelled" && can(Perm.NOMINATION_WRITE);
  const byPosition = new Map(n.formulas.map((f) => [`${f.office_type_id}:${f.position}`, f]));

  async function saveFormula(
    slot: SlotOut,
    position: number,
    owner: string,
    substitute: string | null,
  ) {
    setActionError(null);
    try {
      await override.run(async (ov) => {
        const { data } = await createFormula({
          path: { nomination_id: nominationId },
          body: {
            office_type_id: slot.office_type_id,
            position,
            owner_person_id: owner,
            substitute_person_id: substitute,
            override: ov,
          },
          throwOnError: true,
        });
        apply(data);
        focusNextEmpty(`slot-${slot.office_type_id}-${position}`);
        return data;
      });
    } catch (error) {
      setActionError(error);
    }
  }

  async function updateMembers(formula: FormulaOut, owner: string, substitute: string | null) {
    setActionError(null);
    try {
      await override.run(async (ov) => {
        const { data } = await updateFormulaMembers({
          path: { formula_id: formula.id },
          body: { owner_person_id: owner, substitute_person_id: substitute, override: ov },
          throwOnError: true,
        });
        apply(data);
        setEditing(null);
        return data;
      });
    } catch (error) {
      setActionError(error);
    }
  }

  return (
    <section>
      <PageHeader
        title={office?.name ?? n.office_code}
        description={
          <>
            <GeoName level={n.geographic_level} id={n.node_id} withLevel /> ·{" "}
            {n.party_id ? partyById.get(n.party_id)?.acronym : "Coalición"} ·{" "}
            {processById.get(n.process_id)?.name}
          </>
        }
        actions={
          <>
            <Badge variant="secondary">{NOMINATION_STATUS[n.status]}</Badge>
            {!n.editable ? (
              <Badge variant="outline">Solo lectura (fuera de tu alcance)</Badge>
            ) : null}
            {editable && draft ? (
              <Button
                onClick={() => action.mutate("submit")}
                disabled={!n.complete || action.isPending}
              >
                Enviar
              </Button>
            ) : null}
            {editable && n.status === "submitted" && can(Perm.NOMINATION_APPROVE) ? (
              <Button onClick={() => action.mutate("approve")} disabled={action.isPending}>
                Aprobar
              </Button>
            ) : null}
            {editable && (draft || can(Perm.NOMINATION_APPROVE)) ? (
              <ConfirmDialog
                trigger={<Button variant="outline">Cancelar postulación</Button>}
                title="¿Cancelar la postulación?"
                description="Se cancelan todas sus fórmulas vigentes. La geografía queda libre para otra postulación."
                confirmLabel="Cancelar postulación"
                destructive
                onConfirm={() => action.mutate("cancel")}
              />
            ) : null}
          </>
        }
      />
      <div className="space-y-4">
        <ProblemAlert error={actionError} />
        {n.warnings?.length ? (
          <Alert>
            <AlertTriangle aria-hidden />
            <AlertTitle>Avisos de validación</AlertTitle>
            <AlertDescription>
              <ul className="list-disc pl-4">
                {n.warnings.map((w) => (
                  <li key={`${w.rule}-${w.formula_id ?? "n"}`}>{w.message}</li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        ) : null}
        <Tabs defaultValue="formulas">
          <TabsList>
            <TabsTrigger value="formulas">Fórmulas</TabsTrigger>
            <TabsTrigger value="validation">Validación</TabsTrigger>
            <TabsTrigger value="history">Historial</TabsTrigger>
          </TabsList>
          <TabsContent value="formulas" className="space-y-6 pt-4">
            <p className="text-sm text-muted-foreground">
              {n.complete
                ? "Todas las posiciones están capturadas."
                : "Captura cada posición: propietaria, suplente y Guardar (o Ctrl+Enter). El cursor pasa sola a la siguiente."}
            </p>
            {n.slots.map((slot) => {
              const slotOffice = officeById.get(slot.office_type_id);
              const hasSubstitute = slotOffice?.has_substitute ?? true;
              return (
                <div key={slot.office_type_id} className="space-y-2">
                  <h2 className="flex items-baseline gap-2 text-base font-semibold">
                    {slot.office_name}
                    <span className="text-sm font-normal text-muted-foreground">
                      {slot.filled} de {slot.expected}
                    </span>
                  </h2>
                  {slot.expected === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      Sin posiciones a registrar (método de RP sin lista o integración municipal en
                      cero).
                    </p>
                  ) : (
                    <ol className="divide-y rounded-lg border">
                      {Array.from({ length: slot.expected }, (_, i) => i + 1).map((position) => {
                        const formula = byPosition.get(`${slot.office_type_id}:${position}`);
                        const rowId = `slot-${slot.office_type_id}-${position}`;
                        const label = `${slot.office_name} ${position}`;
                        return (
                          <li
                            key={position}
                            className="grid grid-cols-[3rem_1fr] items-center gap-2 px-3 py-2"
                          >
                            <span className="text-sm font-medium text-muted-foreground" aria-hidden>
                              {position}
                            </span>
                            {formula && editing !== formula.id ? (
                              <div className="grid items-center gap-2 md:grid-cols-[1fr_1fr_auto_auto]">
                                <Member label="Propietaria" member={formula.owner} />
                                <Member label="Suplente" member={formula.substitute} />
                                <Badge variant="outline">{FORMULA_STATUS[formula.status]}</Badge>
                                <FormulaActions
                                  formula={formula}
                                  hasSubstitute={hasSubstitute}
                                  editable={editable}
                                  draft={draft}
                                  onEdit={() => setEditing(formula.id)}
                                  onChanged={apply}
                                  override={override}
                                />
                              </div>
                            ) : formula ? (
                              <CaptureRow
                                rowId={`edit-${formula.id}`}
                                label={label}
                                hasSubstitute={hasSubstitute}
                                initial={{
                                  owner: formula.owner
                                    ? {
                                        id: formula.owner.person_id,
                                        label: formula.owner.full_name,
                                      }
                                    : null,
                                  substitute: formula.substitute
                                    ? {
                                        id: formula.substitute.person_id,
                                        label: formula.substitute.full_name,
                                      }
                                    : null,
                                }}
                                onSave={(v) =>
                                  updateMembers(
                                    formula,
                                    v.owner?.id ?? "",
                                    v.substitute?.id ?? null,
                                  )
                                }
                                onCancel={() => setEditing(null)}
                              />
                            ) : editable && draft ? (
                              <CaptureRow
                                rowId={rowId}
                                label={label}
                                hasSubstitute={hasSubstitute}
                                onSave={(v) =>
                                  saveFormula(
                                    slot,
                                    position,
                                    v.owner?.id ?? "",
                                    v.substitute?.id ?? null,
                                  )
                                }
                              />
                            ) : (
                              <span className="text-sm text-muted-foreground">Vacante</span>
                            )}
                          </li>
                        );
                      })}
                    </ol>
                  )}
                </div>
              );
            })}
          </TabsContent>
          <TabsContent value="validation" className="pt-4">
            <ValidationPanel nominationId={nominationId} />
          </TabsContent>
          <TabsContent value="history" className="pt-4">
            <HistoryPanel nominationId={nominationId} />
          </TabsContent>
        </Tabs>
      </div>
      {override.dialog}
    </section>
  );
}

function Member({ label, member }: { label: string; member: FormulaOut["owner"] }) {
  return (
    <div className="min-w-0">
      <span className="sr-only">{label}: </span>
      {member ? (
        <>
          <span className="truncate">{member.full_name}</span>
          {member.sex ? (
            <span className="ml-1 text-xs text-muted-foreground">
              ({SEX_LABELS[member.sex] ?? member.sex})
            </span>
          ) : null}
        </>
      ) : (
        <span className="text-muted-foreground">—</span>
      )}
    </div>
  );
}

function ValidationPanel({ nominationId }: { nominationId: string }) {
  const validation = useQuery(validateNominationOptions({ path: { nomination_id: nominationId } }));
  if (validation.isError) return <ProblemAlert error={validation.error} />;
  if (!validation.data) return <p className="text-muted-foreground">Validando…</p>;
  return validation.data.length ? (
    <ul className="space-y-2">
      {validation.data.map((v) => (
        <li key={`${v.rule}-${v.formula_id ?? "n"}`} className="flex items-start gap-2 text-sm">
          <Badge variant={v.severity === "blocking" ? "destructive" : "secondary"}>
            {v.severity === "blocking" ? "Bloquea" : "Aviso"}
          </Badge>
          {v.message}
        </li>
      ))}
    </ul>
  ) : (
    <p className="flex items-center gap-2 text-sm">
      <CheckCircle2 className="size-4 text-green-600" aria-hidden /> Cumple todas las reglas
      activas, incluida la paridad.
    </p>
  );
}

function HistoryPanel({ nominationId }: { nominationId: string }) {
  const history = useQuery(getNominationHistoryOptions({ path: { nomination_id: nominationId } }));
  if (history.isError) return <ProblemAlert error={history.error} />;
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <caption className="sr-only">Historial de estatus</caption>
        <thead className="bg-muted/50 text-left text-muted-foreground">
          <tr>
            <th scope="col" className="px-3 py-2">
              Fecha
            </th>
            <th scope="col" className="px-3 py-2">
              Posición
            </th>
            <th scope="col" className="px-3 py-2">
              Cambio
            </th>
            <th scope="col" className="px-3 py-2">
              Motivo
            </th>
          </tr>
        </thead>
        <tbody>
          {(history.data ?? []).map((h) => (
            <tr key={`${h.formula_id}-${h.changed_at}-${h.to_status}`} className="border-t">
              <td className="px-3 py-2">{formatDateTime(h.changed_at)}</td>
              <td className="px-3 py-2">
                {h.office_code} {h.position}
              </td>
              <td className="px-3 py-2">
                {h.from_status ? `${FORMULA_STATUS[h.from_status]} → ` : ""}
                {FORMULA_STATUS[h.to_status]}
              </td>
              <td className="px-3 py-2">{h.reason ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
