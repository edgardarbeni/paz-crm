import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import type { ScopeIn, ScopeLevel } from "@/client/types.gen";
import { AsyncCombobox, type ComboItem } from "@/components/async-combobox";
import { Button } from "@/components/ui/button";
import { GeoName } from "@/features/candidacies/geo-name";
import { GEO_LEVEL_LABELS } from "@/lib/labels";
import { GEO_SEARCH_HINTS, type GeoSearchLevel, searchGeoItems } from "@/lib/search";

const SCOPE_LEVELS: ScopeLevel[] = [
  "national",
  "electoral_region",
  "state",
  "federal_district",
  "local_district",
  "municipality",
  "section",
];

export type ScopeRow = ScopeIn & { label?: string };

/** The scope of one grant (D-34, D-101): nodes the grant's role is limited to. Controlled: the
 * caller owns the rows and decides when to save. */
export function ScopeRowsEditor({
  rows,
  onChange,
  editable,
  idPrefix,
}: {
  rows: ScopeRow[];
  onChange: (rows: ScopeRow[]) => void;
  editable: boolean;
  idPrefix: string;
}) {
  const [level, setLevel] = useState<ScopeLevel>("municipality");
  const [node, setNode] = useState<ComboItem | null>(null);
  return (
    <div className="space-y-2">
      {rows.length ? (
        <ul className="divide-y rounded-lg border">
          {rows.map((row, index) => (
            <li
              key={`${row.level}-${row.node_id ?? "all"}`}
              className="flex items-center justify-between px-3 py-1.5 text-sm"
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
                  onClick={() => onChange(rows.filter((_, i) => i !== index))}
                >
                  <Trash2 aria-hidden />
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">
          Sin alcance: este rol no ve geografía ni datos ligados a ella (denegación por defecto).
        </p>
      )}
      {editable ? (
        <div className="flex flex-wrap items-center gap-2">
          <select
            id={`${idPrefix}-level`}
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
              placeholder={GEO_SEARCH_HINTS[level]}
              className="min-w-64 flex-1"
            />
          ) : null}
          <Button
            variant="outline"
            size="sm"
            disabled={level !== "national" && !node}
            onClick={() => {
              onChange([
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
            <Plus aria-hidden /> Agregar alcance
          </Button>
        </div>
      ) : null}
    </div>
  );
}
