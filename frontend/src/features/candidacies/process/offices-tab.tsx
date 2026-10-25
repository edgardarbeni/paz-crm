import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  configureProcessOfficesMutation,
  listOfficeTypesOptions,
  listProcessOfficesOptions,
  listProcessOfficesQueryKey,
} from "@/client/@tanstack/react-query.gen";
import type { ProcessOfficeIn } from "@/client/types.gen";
import { ProblemAlert } from "@/components/problem-alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { NOMINATION_KIND, RP_METHOD } from "@/lib/labels";

const selectClass =
  "h-8 rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-40";

/** Which offices are up for election and how they compose (D-23, D-25, D-21). */
export function OfficesTab({ processId, editable }: { processId: string; editable: boolean }) {
  const queryClient = useQueryClient();
  const configs = useQuery(listProcessOfficesOptions({ path: { process_id: processId } }));
  const offices = useQuery(listOfficeTypesOptions());
  const [rows, setRows] = useState<ProcessOfficeIn[]>([]);
  useEffect(() => {
    if (configs.data) {
      setRows(
        configs.data.map(({ office_code: _c, office_name: _n, ...config }) => ({
          ...config,
          rp_method_params: config.rp_method_params ?? {},
        })),
      );
    }
  }, [configs.data]);
  const save = useMutation({
    ...configureProcessOfficesMutation(),
    onSuccess: (data) => {
      queryClient.setQueryData(
        listProcessOfficesQueryKey({ path: { process_id: processId } }),
        data,
      );
      toast.success("Cargos guardados.");
    },
  });
  const byId = new Map((offices.data ?? []).map((o) => [o.id, o]));
  const slateHeads = rows
    .map((row) => byId.get(row.office_type_id))
    .filter((office) => office?.nomination_kind === "slate");

  function patch(index: number, change: Partial<ProcessOfficeIn>) {
    setRows((current) => current.map((row, i) => (i === index ? { ...row, ...change } : row)));
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Habilita los cargos que van a elección. Los integrantes de planilla (sindicaturas,
        regidurías, concejalías) se ligan a su cargo principal; sus cantidades por municipio se
        capturan en la pestaña Municipios.
      </p>
      <ProblemAlert error={save.error ?? configs.error} />
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <caption className="sr-only">Cargos del proceso</caption>
          <thead className="bg-muted/50 text-left text-muted-foreground">
            <tr>
              <th scope="col" className="px-3 py-2">
                En elección
              </th>
              <th scope="col" className="px-3 py-2">
                Cargo
              </th>
              <th scope="col" className="px-3 py-2">
                Posiciones
              </th>
              <th scope="col" className="px-3 py-2">
                Integra la planilla de
              </th>
              <th scope="col" className="px-3 py-2">
                Método de RP
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => {
              const office = byId.get(row.office_type_id);
              if (!office) return null;
              const label = `${office.name}`;
              return (
                <tr key={row.office_type_id} className="border-t">
                  <td className="px-3 py-2">
                    <Checkbox
                      aria-label={`${label} en elección`}
                      checked={row.is_enabled}
                      disabled={!editable}
                      onCheckedChange={(checked) => patch(index, { is_enabled: checked === true })}
                    />
                  </td>
                  <td className="px-3 py-2">
                    <div className="font-medium">{office.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {NOMINATION_KIND[office.nomination_kind]}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <Input
                      type="number"
                      min={1}
                      max={500}
                      aria-label={`Posiciones de ${label}`}
                      placeholder={
                        office.default_positions ? String(office.default_positions) : "—"
                      }
                      className="w-24"
                      disabled={
                        !editable ||
                        office.nomination_kind === "single" ||
                        office.nomination_kind === "slate"
                      }
                      value={row.positions ?? ""}
                      onChange={(event) =>
                        patch(index, {
                          positions: event.target.value ? Number(event.target.value) : null,
                        })
                      }
                    />
                  </td>
                  <td className="px-3 py-2">
                    <select
                      aria-label={`Planilla de ${label}`}
                      className={selectClass}
                      disabled={!editable || office.nomination_kind === "slate"}
                      value={row.slate_parent_office_type_id ?? ""}
                      onChange={(event) =>
                        patch(index, { slate_parent_office_type_id: event.target.value || null })
                      }
                    >
                      <option value="">
                        {office.nomination_kind === "member" ? "Selecciona…" : "Se postula sola"}
                      </option>
                      {slateHeads.map((head) =>
                        head && head.id !== office.id ? (
                          <option key={head.id} value={head.id}>
                            {head.name}
                          </option>
                        ) : null,
                      )}
                    </select>
                  </td>
                  <td className="px-3 py-2">
                    {office.principle === "rp" ? (
                      <select
                        aria-label={`Método de RP de ${label}`}
                        className={selectClass}
                        disabled={!editable}
                        value={row.rp_method ?? ""}
                        onChange={(event) =>
                          patch(index, {
                            rp_method: (event.target.value || null) as ProcessOfficeIn["rp_method"],
                          })
                        }
                      >
                        <option value="">Sin definir</option>
                        {Object.entries(RP_METHOD).map(([value, text]) => (
                          <option key={value} value={value}>
                            {text}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {editable ? (
        <Button
          onClick={() => save.mutate({ path: { process_id: processId }, body: rows })}
          disabled={save.isPending}
        >
          {save.isPending ? "Guardando…" : "Guardar cargos"}
        </Button>
      ) : null}
    </div>
  );
}
