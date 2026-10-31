import { X } from "lucide-react";
import { AsyncCombobox, type ComboItem } from "@/components/async-combobox";
import { Button } from "@/components/ui/button";
import { searchGeoItems } from "@/lib/search";

export const KIND_LEVEL = {
  federal: "federal_district",
  local: "local_district",
  sectional: "section",
} as const;

/** Nodes of a coordination's territory: districts or sections, added one by one. */
export function TerritoryEditor({
  kind,
  nodes,
  onChange,
}: {
  kind: keyof typeof KIND_LEVEL;
  nodes: ComboItem[];
  onChange: (nodes: ComboItem[]) => void;
}) {
  const level = KIND_LEVEL[kind];
  return (
    <div className="grid gap-2">
      <AsyncCombobox
        id={`territory-${kind}`}
        label="Agregar territorio"
        value={null}
        onChange={(item) => {
          if (item && !nodes.some((n) => n.id === item.id)) onChange([...nodes, item]);
        }}
        queryKey={["territory", level]}
        search={(term) => searchGeoItems(term, [level])}
        minChars={1}
        placeholder={kind === "sectional" ? "Número de sección" : "Número de distrito"}
      />
      {nodes.length ? (
        <ul className="flex flex-wrap gap-1" aria-label="Territorio">
          {nodes.map((node) => (
            <li
              key={node.id}
              className="flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs"
            >
              {node.label}
              <Button
                type="button"
                size="icon-sm"
                variant="ghost"
                aria-label={`Quitar ${node.label}`}
                onClick={() => onChange(nodes.filter((n) => n.id !== node.id))}
              >
                <X aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">Sin territorio todavía.</p>
      )}
    </div>
  );
}
