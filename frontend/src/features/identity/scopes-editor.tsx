import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  getUserScopesOptions,
  getUserScopesQueryKey,
  setUserScopesMutation,
} from "@/client/@tanstack/react-query.gen";
import type { ScopeIn, ScopeLevel } from "@/client/types.gen";
import { AsyncCombobox, type ComboItem } from "@/components/async-combobox";
import { ProblemAlert } from "@/components/problem-alert";
import { Button } from "@/components/ui/button";
import { GeoName } from "@/features/candidacies/geo-name";
import { GEO_LEVEL_LABELS } from "@/lib/labels";
import { type GeoSearchLevel, searchGeoItems } from "@/lib/search";

const SCOPE_LEVELS: ScopeLevel[] = [
  "national",
  "electoral_region",
  "state",
  "federal_district",
  "local_district",
  "municipality",
  "section",
];

/** Geographic scope (D-34): the user sees and edits only what lies under these nodes. */
export function ScopesEditor({ userId, editable }: { userId: string; editable: boolean }) {
  const queryClient = useQueryClient();
  const scopes = useQuery(getUserScopesOptions({ path: { user_id: userId } }));
  const [rows, setRows] = useState<(ScopeIn & { label?: string })[]>([]);
  const [level, setLevel] = useState<ScopeLevel>("municipality");
  const [node, setNode] = useState<ComboItem | null>(null);
  useEffect(() => {
    if (scopes.data) setRows(scopes.data.map((s) => ({ level: s.level, node_id: s.node_id })));
  }, [scopes.data]);
  const save = useMutation({
    ...setUserScopesMutation(),
    onSuccess: (data) => {
      queryClient.setQueryData(getUserScopesQueryKey({ path: { user_id: userId } }), data);
      toast.success("Alcance actualizado.");
    },
  });
  return (
    <div className="space-y-3">
      <ProblemAlert error={save.error ?? scopes.error} />
      {rows.length ? (
        <ul className="divide-y rounded-lg border">
          {rows.map((row, index) => (
            <li
              key={`${row.level}-${row.node_id ?? "all"}`}
              className="flex items-center justify-between px-3 py-2 text-sm"
            >
              <span>
                <span className="text-muted-foreground">{GEO_LEVEL_LABELS[row.level]}: </span>
                {row.label ??
                  (row.node_id ? <GeoName level={row.level} id={row.node_id} /> : "Todo el país")}
              </span>
              {editable ? (
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Quitar alcance ${GEO_LEVEL_LABELS[row.level]}`}
                  onClick={() => setRows(rows.filter((_, i) => i !== index))}
                >
                  <Trash2 aria-hidden />
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">
          Sin alcance: el usuario no ve geografía ni datos ligados a ella (denegación por defecto).
        </p>
      )}
      {editable ? (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed p-3">
          <select
            aria-label="Nivel del alcance"
            value={level}
            onChange={(e) => {
              setLevel(e.target.value as ScopeLevel);
              setNode(null);
            }}
            className="h-8 rounded-lg border border-input bg-transparent px-2 text-sm"
          >
            {SCOPE_LEVELS.map((l) => (
              <option key={l} value={l}>
                {GEO_LEVEL_LABELS[l]}
              </option>
            ))}
          </select>
          {level !== "national" ? (
            <AsyncCombobox
              label={`Buscar ${GEO_LEVEL_LABELS[level]?.toLowerCase()}`}
              value={node}
              onChange={setNode}
              queryKey={["geo-search", level]}
              search={(term) => searchGeoItems(term, [level as GeoSearchLevel])}
              minChars={1}
              className="min-w-64 flex-1"
            />
          ) : null}
          <Button
            variant="outline"
            size="sm"
            disabled={level !== "national" && !node}
            onClick={() => {
              setRows([
                ...rows,
                {
                  level,
                  node_id: level === "national" ? null : (node?.id ?? null),
                  label: node?.label,
                },
              ]);
              setNode(null);
            }}
          >
            <Plus aria-hidden /> Agregar
          </Button>
          <Button
            size="sm"
            className="ml-auto"
            disabled={save.isPending}
            onClick={() =>
              save.mutate({
                path: { user_id: userId },
                body: { scopes: rows.map(({ label: _l, ...s }) => s) },
              })
            }
          >
            Guardar alcance
          </Button>
        </div>
      ) : null}
    </div>
  );
}
