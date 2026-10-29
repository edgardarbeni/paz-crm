import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowUpRight, ChevronRight, Search } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { getGeoNodeChildrenOptions } from "@/client/@tanstack/react-query.gen";
import { listGeoNodes } from "@/client/sdk.gen";
import type { GeoChildGroup, GeoNodeOut } from "@/client/types.gen";
import { ProblemAlert } from "@/components/problem-alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import type { GeoNodeLevel } from "@/features/candidacies/geo-name";
import { useDebounced } from "@/hooks/use-debounced";
import { GEO_LEVEL_LABELS, GEO_LEVEL_PLURALS } from "@/lib/labels";
import { geoChildLabel } from "@/lib/search";
import { cn } from "@/lib/utils";

const PAGE = 50;
/** Groups longer than this get a filter box. */
const FILTER_FROM = 12;
/** The first group opens by itself only when short; a long one would hide the other groups. */
const AUTO_OPEN_MAX = 30;
const NAMED = new Set(["state", "municipality", "locality", "neighborhood"]);

export interface ChildPointer {
  level: string;
  id: string;
}

/**
 * "Contiene": one collapsible group per child level with its count, listing the children right
 * here (paged, filterable) so the user can jump to them without leaving the map. The open groups
 * are reported so the map can draw their layers; pointing at a child outlines it on the map.
 */
export function NodeChildren({
  level,
  nodeId,
  onOpenChange,
  onPoint,
  className,
}: {
  level: string;
  nodeId: string;
  onOpenChange: (levels: string[]) => void;
  onPoint: (child: ChildPointer | null) => void;
  className?: string;
}) {
  const groups = useQuery(
    getGeoNodeChildrenOptions({ path: { level: level as GeoNodeLevel, node_id: nodeId } }),
  );
  const [open, setOpen] = useState<string[] | null>(null);
  const nonEmpty = groups.data?.items.filter((group) => group.count > 0) ?? [];
  const first = nonEmpty[0];
  const current = open ?? (first && first.count <= AUTO_OPEN_MAX ? [first.level] : []);

  const openKey = current.join(",");
  useEffect(() => {
    onOpenChange(openKey ? openKey.split(",") : []);
  }, [openKey, onOpenChange]);

  function toggle(child: string) {
    setOpen(current.includes(child) ? current.filter((l) => l !== child) : [...current, child]);
  }

  if (groups.data && groups.data.items.length === 0) return null;
  return (
    <Card className={cn("min-h-0 gap-3", className)}>
      <CardHeader>
        <CardTitle>
          <h2>Contiene</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2">
        <ProblemAlert error={groups.error} />
        {groups.isPending ? (
          <div className="space-y-2 px-3" aria-busy="true">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-8" />
            ))}
          </div>
        ) : nonEmpty.length === 0 ? (
          <p className="px-3 text-muted-foreground">Nada dentro de tu alcance.</p>
        ) : (
          <div className="space-y-1">
            {nonEmpty.map((group) => (
              <ChildGroup
                key={group.level}
                group={group}
                nodeId={nodeId}
                open={current.includes(group.level)}
                onToggle={() => toggle(group.level)}
                onPoint={onPoint}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ChildGroup({
  group,
  nodeId,
  open,
  onToggle,
  onPoint,
}: {
  group: GeoChildGroup;
  nodeId: string;
  open: boolean;
  onToggle: () => void;
  onPoint: (child: ChildPointer | null) => void;
}) {
  const panelId = useId();
  const plural = GEO_LEVEL_PLURALS[group.level] ?? group.level;
  return (
    <section aria-label={plural}>
      {/* Sticky so a long open list can be closed without scrolling back up. */}
      <h3 className="sticky top-0 z-10 bg-card">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={onToggle}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-semibold transition-colors hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
        >
          <ChevronRight
            aria-hidden
            className={cn(
              "size-4 shrink-0 text-muted-foreground transition-transform",
              open && "rotate-90",
            )}
          />
          <span className="flex-1">{plural}</span>
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground tabular-nums">
            {group.count.toLocaleString("es-MX")}
          </span>
        </button>
      </h3>
      {open ? (
        <div id={panelId} className="pb-2">
          <ChildList group={group} nodeId={nodeId} onPoint={onPoint} />
        </div>
      ) : null}
    </section>
  );
}

function ChildList({
  group,
  nodeId,
  onPoint,
}: {
  group: GeoChildGroup;
  nodeId: string;
  onPoint: (child: ChildPointer | null) => void;
}) {
  const named = NAMED.has(group.level);
  const [term, setTerm] = useState("");
  const typed = useDebounced(term.trim(), 300);
  // Unnamed levels (districts, sections) are found by number; a single letter is not a search.
  const q = named ? (typed.length >= 2 || /^\d+$/.test(typed) ? typed : "") : typed;
  const filter = { [group.parent_filter]: nodeId };
  const children = useInfiniteQuery({
    queryKey: ["geo-children", group.level, group.parent_filter, nodeId, q],
    queryFn: async ({ pageParam, signal }) => {
      const { data } = await listGeoNodes({
        path: { level: group.level },
        query: { ...filter, q: q || undefined, cursor: pageParam, limit: PAGE, sort: "code" },
        signal,
        throwOnError: true,
      });
      return data;
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => (last.has_more ? (last.next_cursor ?? undefined) : undefined),
    staleTime: 5 * 60_000,
  });
  const items: GeoNodeOut[] = children.data?.pages.flatMap((page) => page.items) ?? [];
  const remaining = q ? null : group.count - items.length;
  const singular = (GEO_LEVEL_LABELS[group.level] ?? "").toLowerCase();

  return (
    <div className="space-y-1 pl-3">
      {group.count > FILTER_FROM ? (
        <div className="relative py-1 pr-1">
          <Search
            aria-hidden
            className="pointer-events-none absolute top-3 left-2.5 size-3.5 text-muted-foreground"
          />
          <Input
            type="search"
            value={term}
            onChange={(event) =>
              setTerm(named ? event.target.value : event.target.value.replace(/\D/g, ""))
            }
            inputMode={named ? "text" : "numeric"}
            aria-label={`Filtrar ${GEO_LEVEL_PLURALS[group.level]?.toLowerCase()}`}
            placeholder={named ? "Número o nombre" : `Número de ${singular}`}
            className="h-8 pl-8 text-sm"
          />
        </div>
      ) : null}
      <ProblemAlert error={children.error} />
      {children.isPending ? (
        <div className="space-y-1.5 py-1 pr-1" aria-busy="true">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-6" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <p className="px-2 py-1 text-sm text-muted-foreground">Sin coincidencias.</p>
      ) : (
        <ul className="pr-1" onMouseLeave={() => onPoint(null)}>
          {items.map((node) => {
            const { code, label } = geoChildLabel(node);
            const point = () => onPoint({ level: node.level, id: node.id });
            return (
              <li key={node.id}>
                <Link
                  to="/geography/$level/$nodeId"
                  params={{ level: node.level, nodeId: node.id }}
                  onMouseEnter={point}
                  onFocus={point}
                  onBlur={() => onPoint(null)}
                  className="flex items-baseline gap-2 rounded-md px-2 py-1 text-sm transition-colors hover:bg-primary/10 hover:text-primary focus-visible:bg-primary/10 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
                >
                  {code ? (
                    <code className="w-9 shrink-0 text-xs text-muted-foreground tabular-nums">
                      {code}
                    </code>
                  ) : null}
                  <span className="truncate">{label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2 px-2 pt-1">
        {children.hasNextPage ? (
          <Button
            variant="ghost"
            size="sm"
            className="-ml-2 h-7"
            disabled={children.isFetchingNextPage}
            onClick={() => children.fetchNextPage()}
          >
            {children.isFetchingNextPage
              ? "Cargando…"
              : remaining && remaining > 0
                ? `Mostrar ${Math.min(PAGE, remaining)} más · quedan ${remaining.toLocaleString("es-MX")}`
                : "Mostrar más"}
          </Button>
        ) : (
          <span />
        )}
        <Link
          to="/geography"
          search={{ level: group.level as never, [group.parent_filter]: nodeId }}
          className="inline-flex items-center gap-1 text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          Ver en el explorador
          <ArrowUpRight aria-hidden className="size-3" />
        </Link>
      </div>
    </div>
  );
}
