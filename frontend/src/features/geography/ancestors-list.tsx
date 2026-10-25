import type { Ancestors } from "@/client/types.gen";
import { GEO_LEVEL_LABELS } from "@/lib/labels";

const ORDER: (keyof Ancestors)[] = [
  "section",
  "municipality",
  "local_district",
  "federal_district",
  "state",
  "electoral_region",
];

export function AncestorsList({ ancestors }: { ancestors: Ancestors }) {
  return (
    <dl
      aria-label="Geografía del punto"
      className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm"
    >
      {ORDER.map((key) => {
        const ref = ancestors[key];
        return (
          <div key={key} className="contents">
            <dt className="text-muted-foreground">{GEO_LEVEL_LABELS[key]}</dt>
            <dd>{ref ? (ref.name ? `${ref.key} · ${ref.name}` : ref.key) : "—"}</dd>
          </div>
        );
      })}
    </dl>
  );
}
