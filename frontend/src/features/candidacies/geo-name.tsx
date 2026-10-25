import { useQuery } from "@tanstack/react-query";
import { getGeoNodeOptions } from "@/client/@tanstack/react-query.gen";
import type { GetGeoNodeData } from "@/client/types.gen";
import { GEO_LEVEL_LABELS } from "@/lib/labels";
import { geoNodeLabel } from "@/lib/search";

export type GeoNodeLevel = GetGeoNodeData["path"]["level"];

/** "Calvillo · Aguascalientes", "Sección 0338 · Aguascalientes" for a node id (cached). */
export function GeoName({
  level,
  id,
  withLevel,
}: {
  level: string;
  id: string | null | undefined;
  withLevel?: boolean;
}) {
  const enabled = !!id && level !== "national";
  const node = useQuery({
    ...getGeoNodeOptions({ path: { level: level as GeoNodeLevel, node_id: id ?? "" } }),
    enabled,
    staleTime: 10 * 60_000,
  });
  if (level === "national") return <>Nacional</>;
  if (!id) return <>—</>;
  if (!node.data) return <>…</>;
  const { label } = geoNodeLabel(node.data);
  // Districts, sections and regions already say what they are.
  const named = ["state", "municipality", "locality", "neighborhood"].includes(level);
  return <>{withLevel && named ? `${GEO_LEVEL_LABELS[level]} ${label}` : label}</>;
}
