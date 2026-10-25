import { useQuery } from "@tanstack/react-query";
import { getGeoNodeOptions } from "@/client/@tanstack/react-query.gen";
import type { GetGeoNodeData } from "@/client/types.gen";
import { GEO_LEVEL_LABELS } from "@/lib/labels";

export type GeoNodeLevel = GetGeoNodeData["path"]["level"];

/** "01-001 · AGUASCALIENTES" for a node id (cached per node). */
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
  const text = node.data
    ? node.data.name
      ? `${node.data.key} · ${node.data.name}`
      : node.data.key
    : "…";
  return <>{withLevel ? `${GEO_LEVEL_LABELS[level]} ${text}` : text}</>;
}
