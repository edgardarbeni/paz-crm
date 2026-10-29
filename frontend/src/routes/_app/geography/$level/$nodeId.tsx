import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { getGeoNodeOptions } from "@/client/@tanstack/react-query.gen";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { GeoName, type GeoNodeLevel } from "@/features/candidacies/geo-name";
import { GeoMap, type LayerId, LEVEL_LAYERS } from "@/features/geography/geo-map";
import { type ChildPointer, NodeChildren } from "@/features/geography/node-children";
import { GEO_LEVEL_LABELS } from "@/lib/labels";

export const Route = createFileRoute("/_app/geography/$level/$nodeId")({ component: NodePage });

const MAP_LAYERS: Record<string, LayerId[]> = {
  electoral_region: ["states"],
  state: ["states", "municipalities"],
  municipality: ["municipalities", "sections"],
  federal_district: ["federal_districts", "sections"],
  local_district: ["local_districts", "sections"],
  section: ["sections", "blocks"],
  locality: ["sections"],
  neighborhood: ["neighborhoods", "sections"],
};

function NodePage() {
  const { level, nodeId } = Route.useParams();
  const node = useQuery({
    ...getGeoNodeOptions({
      path: { level: level as GeoNodeLevel, node_id: nodeId },
      query: { geometry: true },
    }),
    // Keep the map mounted while moving from a node to one of its children.
    placeholderData: keepPreviousData,
  });
  const [openLevels, setOpenLevels] = useState<string[]>([]);
  const [pointed, setPointed] = useState<ChildPointer | null>(null);
  // biome-ignore lint/correctness/useExhaustiveDependencies: reset the outline on every node
  useEffect(() => setPointed(null), [nodeId]);
  const onOpenChange = useCallback((levels: string[]) => setOpenLevels(levels), []);
  // The node's own layers plus those of the groups open in "Contiene".
  const layersKey = [
    ...(MAP_LAYERS[level] ?? ["states"]),
    ...openLevels.flatMap((l) => LEVEL_LAYERS[l] ?? []),
  ].join(",");
  const visible = useMemo(() => [...new Set(layersKey.split(","))] as LayerId[], [layersKey]);
  const hoveredLayer = pointed ? LEVEL_LAYERS[pointed.level] : undefined;
  const hovered = useMemo(
    () => (pointed && hoveredLayer ? { layer: hoveredLayer, id: pointed.id } : null),
    [pointed, hoveredLayer],
  );
  if (node.isError) return <ProblemAlert error={node.error} />;
  const n = node.data;
  if (!n) return <p className="text-muted-foreground">Cargando…</p>;
  // Sections carry full ancestors; other levels expose their parents' ids.
  const parents: [string, string | null | undefined][] = n.ancestors
    ? Object.entries(n.ancestors)
        .filter(([key, ref]) => ref && key !== level)
        .map(([key, ref]) => [key, (ref as { id: string }).id])
    : [
        ["municipality", n.municipality_id],
        ["local_district", n.local_district_id],
        ["federal_district", n.federal_district_id],
        ["state", n.state_id],
        ["electoral_region", n.electoral_region_id],
      ];
  const ancestors = parents.filter(
    (entry): entry is [string, string] => !!entry[1] && entry[0] !== level,
  );
  return (
    <section>
      <PageHeader
        title={n.name ? `${n.key} · ${n.name}` : n.key}
        description={`${GEO_LEVEL_LABELS[n.level]}${n.block_count != null ? ` · ${n.block_count.toLocaleString("es-MX")} manzanas` : ""}`}
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <GeoMap visible={visible} highlight={n.geometry} bbox={n.bbox} hovered={hovered} />
        {/* As tall as the map on wide screens; "Contiene" scrolls inside the remaining space. */}
        <div className="flex flex-col gap-4 lg:h-[70vh]">
          {ancestors.length ? (
            <Card className="shrink-0">
              <CardHeader>
                <CardTitle>
                  <h2>Pertenece a</h2>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <dl className="space-y-2 text-sm">
                  {ancestors.map(([key, id]) => (
                    <div key={key}>
                      <dt className="text-xs text-muted-foreground">{GEO_LEVEL_LABELS[key]}</dt>
                      <dd>
                        <Link
                          to="/geography/$level/$nodeId"
                          params={{ level: key, nodeId: id }}
                          className="underline-offset-4 hover:underline"
                        >
                          <GeoName level={key} id={id} />
                        </Link>
                      </dd>
                    </div>
                  ))}
                </dl>
              </CardContent>
            </Card>
          ) : null}
          <NodeChildren
            key={`${level}:${nodeId}`}
            level={level}
            nodeId={nodeId}
            onOpenChange={onOpenChange}
            onPoint={setPointed}
            className="max-h-[32rem] lg:max-h-none lg:flex-1"
          />
        </div>
      </div>
    </section>
  );
}
