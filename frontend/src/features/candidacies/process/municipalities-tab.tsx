import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  configureMunicipalitiesMutation,
  listMunicipalitySettingsOptions,
  listMunicipalitySettingsQueryKey,
} from "@/client/@tanstack/react-query.gen";
import { listGeoNodes } from "@/client/sdk.gen";
import type { GeoNodeOut, MunicipalitySettingIn } from "@/client/types.gen";
import { ProblemAlert } from "@/components/problem-alert";
import { SearchInput } from "@/components/search-input";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ELECTION_REGIME } from "@/lib/labels";

async function allMunicipalities(stateId: string): Promise<GeoNodeOut[]> {
  const items: GeoNodeOut[] = [];
  let cursor: string | null | undefined;
  do {
    const { data } = await listGeoNodes({
      path: { level: "municipality" },
      query: { state_id: stateId, limit: 200, cursor, sort: "code" },
      throwOnError: true,
    });
    items.push(...data.items);
    cursor = data.has_more ? data.next_cursor : null;
  } while (cursor);
  return items;
}

type Row = MunicipalitySettingIn & { key: string; name: string; dirty: boolean };
type CountField = "mr_councilor_count" | "rp_councilor_count" | "syndic_count";
const COUNTS: [CountField, string][] = [
  ["syndic_count", "Sindicaturas"],
  ["mr_councilor_count", "Regidurías MR"],
  ["rp_councilor_count", "Regidurías RP"],
];

/** Per-municipality composition (D-24..D-26): captured or pasted by the user, never assumed. */
export function MunicipalitiesTab({
  processId,
  stateId,
  editable,
}: {
  processId: string;
  stateId: string;
  editable: boolean;
}) {
  const queryClient = useQueryClient();
  const municipalities = useQuery({
    queryKey: ["all-municipalities", stateId],
    queryFn: () => allMunicipalities(stateId),
    staleTime: 10 * 60_000,
  });
  const settings = useQuery(listMunicipalitySettingsOptions({ path: { process_id: processId } }));
  const [rows, setRows] = useState<Row[]>([]);
  const [filter, setFilter] = useState("");
  useEffect(() => {
    if (!municipalities.data || !settings.data) return;
    const current = new Map(settings.data.map((s) => [s.municipality_id, s]));
    setRows(
      municipalities.data.map((m) => {
        const s = current.get(m.id);
        return {
          municipality_id: m.id,
          key: m.key,
          name: m.name ?? "",
          election_regime: s?.election_regime ?? "party_based",
          mr_councilor_count: s?.mr_councilor_count ?? 0,
          rp_councilor_count: s?.rp_councilor_count ?? 0,
          syndic_count: s?.syndic_count ?? 0,
          dirty: false,
        };
      }),
    );
  }, [municipalities.data, settings.data]);
  const save = useMutation({
    ...configureMunicipalitiesMutation(),
    onSuccess: (data) => {
      queryClient.setQueryData(
        listMunicipalitySettingsQueryKey({ path: { process_id: processId } }),
        data,
      );
      toast.success("Integración de ayuntamientos guardada.");
    },
  });
  const visible = useMemo(() => {
    const term = filter.trim().toLowerCase();
    return term ? rows.filter((r) => `${r.key} ${r.name}`.toLowerCase().includes(term)) : rows;
  }, [rows, filter]);
  const dirty = rows.filter((r) => r.dirty);

  function patch(id: string, change: Partial<Row>) {
    setRows((current) =>
      current.map((r) => (r.municipality_id === id ? { ...r, ...change, dirty: true } : r)),
    );
  }

  /** Paste a column from a spreadsheet: one value per line, applied from the focused row down. */
  function onPaste(
    event: React.ClipboardEvent<HTMLInputElement>,
    startId: string,
    field: CountField,
  ) {
    const values = event.clipboardData
      .getData("text")
      .split(/\r?\n/)
      .map((v) => v.trim())
      .filter(Boolean);
    if (values.length < 2) return;
    event.preventDefault();
    const start = visible.findIndex((r) => r.municipality_id === startId);
    const targets = new Map(
      visible
        .slice(start, start + values.length)
        .map((r, i) => [r.municipality_id, Number(values[i]) || 0]),
    );
    setRows((current) =>
      current.map((r) =>
        targets.has(r.municipality_id)
          ? { ...r, [field]: targets.get(r.municipality_id), dirty: true }
          : r,
      ),
    );
    toast.info(`Se pegaron ${targets.size} valores.`);
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Captura cuántas sindicaturas y regidurías integra cada ayuntamiento según la ley local.
        Puedes pegar una columna copiada de una hoja de cálculo en cualquier celda: se aplica de esa
        fila hacia abajo.
      </p>
      <ProblemAlert error={save.error ?? municipalities.error ?? settings.error} />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <SearchInput value={filter} onChange={setFilter} label="Filtrar municipios" />
        {editable ? (
          <Button
            disabled={!dirty.length || save.isPending}
            onClick={() =>
              save.mutate({
                path: { process_id: processId },
                body: dirty.map(({ key: _k, name: _n, dirty: _d, ...row }) => row),
              })
            }
          >
            {save.isPending ? "Guardando…" : `Guardar ${dirty.length || ""} cambios`}
          </Button>
        ) : null}
      </div>
      <div className="max-h-[60vh] overflow-auto rounded-lg border">
        <table className="w-full text-sm">
          <caption className="sr-only">Integración de ayuntamientos</caption>
          <thead className="sticky top-0 bg-muted text-left text-muted-foreground">
            <tr>
              <th scope="col" className="px-3 py-2">
                Municipio
              </th>
              <th scope="col" className="px-3 py-2">
                Régimen
              </th>
              {COUNTS.map(([, label]) => (
                <th key={label} scope="col" className="px-3 py-2">
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {municipalities.isPending ? (
              <tr>
                <td colSpan={5} className="px-3 py-4 text-muted-foreground">
                  Cargando municipios…
                </td>
              </tr>
            ) : null}
            {visible.map((row) => {
              const normative = row.election_regime === "normative_system";
              return (
                <tr
                  key={row.municipality_id}
                  className={row.dirty ? "border-t bg-brand-soft" : "border-t"}
                >
                  <th scope="row" className="px-3 py-1.5 text-left font-normal">
                    <span className="font-mono text-xs text-muted-foreground">{row.key}</span>{" "}
                    {row.name}
                  </th>
                  <td className="px-3 py-1.5">
                    <select
                      aria-label={`Régimen de ${row.name}`}
                      disabled={!editable}
                      value={row.election_regime}
                      onChange={(e) =>
                        patch(row.municipality_id, {
                          election_regime: e.target.value as Row["election_regime"],
                        })
                      }
                      className="h-7 rounded-md border border-input bg-transparent px-1 text-sm"
                    >
                      {Object.entries(ELECTION_REGIME).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </td>
                  {COUNTS.map(([field, label]) => (
                    <td key={field} className="px-3 py-1.5">
                      <Input
                        type="number"
                        min={0}
                        max={100}
                        aria-label={`${label} de ${row.name}`}
                        disabled={!editable || normative}
                        value={row[field] ?? 0}
                        onPaste={(e) => onPaste(e, row.municipality_id, field)}
                        onChange={(e) =>
                          patch(row.municipality_id, { [field]: Number(e.target.value) || 0 })
                        }
                        className="h-7 w-20"
                      />
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
