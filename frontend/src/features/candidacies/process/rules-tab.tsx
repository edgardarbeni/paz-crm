import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  configureProcessRulesMutation,
  listProcessOfficesOptions,
  listProcessRulesOptions,
  listProcessRulesQueryKey,
  listValidationRulesOptions,
} from "@/client/@tanstack/react-query.gen";
import type { ProcessRuleIn } from "@/client/types.gen";
import { LabeledToggle } from "@/components/labeled-toggle";
import { ProblemAlert } from "@/components/problem-alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SEVERITY } from "@/lib/labels";

const PARAM_LABELS: Record<string, string> = {
  min_female_ratio: "Proporción mínima de mujeres (0–1)",
  allow_male_owner_female_substitute: "Permitir propietario hombre con suplente mujer",
};

type Row = ProcessRuleIn & { defaults: Record<string, unknown> };

/** Rule engine configuration (D-28, D-67). Nothing electoral is on by default. */
export function RulesTab({ processId, editable }: { processId: string; editable: boolean }) {
  const queryClient = useQueryClient();
  const configured = useQuery(listProcessRulesOptions({ path: { process_id: processId } }));
  const catalog = useQuery(listValidationRulesOptions());
  const offices = useQuery(listProcessOfficesOptions({ path: { process_id: processId } }));
  const [rows, setRows] = useState<Row[]>([]);
  const [newRule, setNewRule] = useState({ rule: "", office: "" });
  useEffect(() => {
    if (!configured.data || !catalog.data) return;
    const defaults = new Map(catalog.data.map((r) => [r.code, r.default_params]));
    setRows(
      configured.data.map((r) => ({
        rule_code: r.rule_code,
        office_type_id: r.office_type_id,
        is_enabled: r.is_enabled,
        severity: r.severity,
        params: r.params ?? {},
        defaults: defaults.get(r.rule_code) ?? {},
      })),
    );
  }, [configured.data, catalog.data]);
  const save = useMutation({
    ...configureProcessRulesMutation(),
    onSuccess: (data) => {
      queryClient.setQueryData(listProcessRulesQueryKey({ path: { process_id: processId } }), data);
      toast.success("Reglas guardadas.");
    },
  });
  const ruleName = new Map((catalog.data ?? []).map((r) => [r.code, r]));
  const officeName = new Map((offices.data ?? []).map((o) => [o.office_type_id, o.office_name]));

  function patch(index: number, change: Partial<Row>) {
    setRows((current) => current.map((r, i) => (i === index ? { ...r, ...change } : r)));
  }

  function setParam(index: number, key: string, value: unknown) {
    setRows((current) =>
      current.map((r, i) => (i === index ? { ...r, params: { ...r.params, [key]: value } } : r)),
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Activa y parametriza las reglas según la ley aplicable. Una regla por cargo prevalece sobre
        la general del proceso. Las bloqueantes impiden guardar salvo excepción autorizada; las
        advertencias solo avisan.
      </p>
      <ProblemAlert error={save.error ?? configured.error} />
      <ul className="space-y-3">
        {rows.map((row, index) => {
          const rule = ruleName.get(row.rule_code);
          const effective = { ...row.defaults, ...row.params };
          return (
            <li
              key={`${row.rule_code}-${row.office_type_id ?? "all"}`}
              className="rounded-lg border p-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="font-medium">{rule?.name ?? row.rule_code}</p>
                  <p className="text-xs text-muted-foreground">
                    {row.office_type_id
                      ? `Solo ${officeName.get(row.office_type_id) ?? "cargo"}`
                      : "Todos los cargos"}
                    {rule?.description ? ` · ${rule.description}` : ""}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <select
                    aria-label={`Severidad de ${rule?.name ?? row.rule_code}`}
                    disabled={!editable}
                    value={row.severity}
                    onChange={(e) => patch(index, { severity: e.target.value as Row["severity"] })}
                    className="h-8 rounded-lg border border-input bg-transparent px-2 text-sm"
                  >
                    {Object.entries(SEVERITY).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                  <LabeledToggle
                    kind="switch"
                    checked={row.is_enabled}
                    disabled={!editable}
                    onCheckedChange={(checked) => patch(index, { is_enabled: checked })}
                  >
                    Activa
                  </LabeledToggle>
                </div>
              </div>
              {Object.keys(row.defaults).length ? (
                <div className="mt-3 flex flex-wrap gap-4">
                  {Object.entries(effective).map(([key, value]) =>
                    typeof value === "boolean" ? (
                      <LabeledToggle
                        key={key}
                        kind="switch"
                        checked={value}
                        disabled={!editable}
                        onCheckedChange={(c) => setParam(index, key, c)}
                      >
                        {PARAM_LABELS[key] ?? key}
                      </LabeledToggle>
                    ) : (
                      <div key={key} className="flex items-center gap-2 text-sm">
                        <Input
                          id={`param-${index}-${key}`}
                          type="number"
                          step="0.05"
                          className="h-7 w-24"
                          disabled={!editable}
                          value={String(value)}
                          onChange={(e) => setParam(index, key, Number(e.target.value))}
                        />
                        <Label htmlFor={`param-${index}-${key}`} className="font-normal">
                          {PARAM_LABELS[key] ?? key}
                        </Label>
                      </div>
                    ),
                  )}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
      {editable ? (
        <div className="flex flex-wrap items-end gap-2 rounded-lg border border-dashed p-3">
          <select
            aria-label="Regla"
            value={newRule.rule}
            onChange={(e) => setNewRule({ ...newRule, rule: e.target.value })}
            className="h-8 rounded-lg border border-input bg-transparent px-2 text-sm"
          >
            <option value="">Regla…</option>
            {(catalog.data ?? []).map((r) => (
              <option key={r.code} value={r.code}>
                {r.name}
              </option>
            ))}
          </select>
          <select
            aria-label="Cargo"
            value={newRule.office}
            onChange={(e) => setNewRule({ ...newRule, office: e.target.value })}
            className="h-8 rounded-lg border border-input bg-transparent px-2 text-sm"
          >
            <option value="">Cargo…</option>
            {(offices.data ?? [])
              .filter((o) => o.is_enabled)
              .map((o) => (
                <option key={o.office_type_id} value={o.office_type_id}>
                  {o.office_name}
                </option>
              ))}
          </select>
          <Button
            variant="outline"
            size="sm"
            disabled={
              !newRule.rule ||
              !newRule.office ||
              rows.some((r) => r.rule_code === newRule.rule && r.office_type_id === newRule.office)
            }
            onClick={() => {
              setRows([
                ...rows,
                {
                  rule_code: newRule.rule,
                  office_type_id: newRule.office,
                  is_enabled: true,
                  severity: "blocking",
                  params: {},
                  defaults: ruleName.get(newRule.rule)?.default_params ?? {},
                },
              ]);
              setNewRule({ rule: "", office: "" });
            }}
          >
            <Plus aria-hidden /> Configuración por cargo
          </Button>
          <Button
            className="ml-auto"
            disabled={save.isPending}
            onClick={() =>
              save.mutate({
                path: { process_id: processId },
                body: rows.map(({ defaults: _d, ...row }) => row),
              })
            }
          >
            {save.isPending ? "Guardando…" : "Guardar reglas"}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
