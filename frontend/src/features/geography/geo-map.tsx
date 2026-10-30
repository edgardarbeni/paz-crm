import "maplibre-gl/dist/maplibre-gl.css";
import * as maplibregl from "maplibre-gl";
// MapLibre locates its worker next to its own module, which a bundler moves; Vite bundles the
// worker (with its shared chunk) and hands over the URL instead.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { useEffect, useRef, useState } from "react";
import { getSession } from "@/lib/auth/session";

maplibregl.setWorkerUrl(workerUrl);

/** Base map (D-72): OpenFreeMap by default, replaceable with VITE_MAP_STYLE_URL. */
const STYLE_URL =
  import.meta.env.VITE_MAP_STYLE_URL || "https://tiles.openfreemap.org/styles/positron";
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export const ELECTORAL_LAYERS = [
  { id: "states", label: "Estados", color: "#1f2937", minzoom: 0 },
  { id: "federal_districts", label: "Distritos federales", color: "#2563eb", minzoom: 5 },
  { id: "local_districts", label: "Distritos locales", color: "#16a34a", minzoom: 5 },
  { id: "municipalities", label: "Municipios", color: "#9333ea", minzoom: 6 },
  { id: "sections", label: "Secciones", color: "#ea580c", minzoom: 9 },
  { id: "neighborhoods", label: "Colonias", color: "#0891b2", minzoom: 12 },
  { id: "blocks", label: "Manzanas", color: "#78716c", minzoom: 14 },
] as const;

export type LayerId = (typeof ELECTORAL_LAYERS)[number]["id"];

/** Tile layer that draws each geographic level (localities have none). */
export const LEVEL_LAYERS: Partial<Record<string, LayerId>> = {
  state: "states",
  federal_district: "federal_districts",
  local_district: "local_districts",
  municipality: "municipalities",
  section: "sections",
  neighborhood: "neighborhoods",
};

// Distinct from every layer color and from the red node highlight.
const HOVER_FILL = "#facc15";
const HOVER_LINE = "#0f172a";

interface GeoMapProps {
  visible: LayerId[];
  /** GeoJSON geometry to highlight and fit (node detail). */
  highlight?: Record<string, unknown> | null;
  bbox?: number[] | null;
  /** Node to outline (e.g. while pointing at it in a list); drawn only where its layer has tiles. */
  hovered?: { layer: LayerId; id: string } | null;
  onClick?: (lngLat: { lng: number; lat: number }) => void;
  /** Point features (e.g. Peace Houses), clustered; `properties.status` picks the color. */
  points?: PointCollection | null;
  /** Click on a single point: its properties. */
  onPointClick?: (properties: Record<string, unknown>) => void;
  /** Fit the camera to the points when they change. */
  fitPoints?: boolean;
  className?: string;
}

export interface PointCollection {
  type: "FeatureCollection";
  features: { type: "Feature"; geometry: unknown; properties: Record<string, unknown> }[];
}

const POINT_COLORS: maplibregl.ExpressionSpecification = [
  "match",
  ["get", "status"],
  "consolidated",
  "#682575",
  "open",
  "#d97706",
  "closed",
  "#94a3b8",
  "#0f766e",
];

/**
 * MapLibre viewer over the API's vector tiles (MVT, D-19). Tiles carry the bearer token via
 * transformRequest, so each user only receives what their scope allows.
 */
export function GeoMap({
  visible,
  highlight,
  bbox,
  hovered,
  onClick,
  points,
  onPointClick,
  fitPoints,
  className,
}: GeoMapProps) {
  const container = useRef<HTMLElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const clickRef = useRef(onClick);
  clickRef.current = onClick;
  const pointClickRef = useRef(onPointClick);
  pointClickRef.current = onPointClick;

  useEffect(() => {
    if (!container.current) return;
    const instance = new maplibregl.Map({
      container: container.current,
      style: STYLE_URL,
      center: [-102.3, 23.6],
      zoom: 4.3,
      attributionControl: { compact: true },
      transformRequest: (url: string) => {
        if (url.includes("/api/v1/geography/tiles/")) {
          const token = getSession().accessToken;
          return { url, headers: token ? { Authorization: `Bearer ${token}` } : {} };
        }
        return { url };
      },
    });
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    instance.on("load", () => {
      const origin = API_BASE || window.location.origin;
      for (const layer of ELECTORAL_LAYERS) {
        instance.addSource(layer.id, {
          type: "vector",
          tiles: [`${origin}/api/v1/geography/tiles/${layer.id}/{z}/{x}/{y}.mvt`],
          minzoom: layer.minzoom,
          maxzoom: 16,
        });
        instance.addLayer({
          id: `${layer.id}-line`,
          type: "line",
          source: layer.id,
          "source-layer": layer.id,
          paint: { "line-color": layer.color, "line-width": layer.id === "states" ? 1.5 : 1 },
          layout: { visibility: "none" },
        });
      }
      instance.addSource("highlight", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      instance.addLayer({
        id: "highlight-fill",
        type: "fill",
        source: "highlight",
        paint: { "fill-color": "#dc2626", "fill-opacity": 0.15 },
      });
      instance.addLayer({
        id: "highlight-line",
        type: "line",
        source: "highlight",
        paint: { "line-color": "#dc2626", "line-width": 2 },
      });
      // Hover outlines go above the highlighted node; hidden until used so their sources do not
      // download tiles for nothing.
      for (const layer of ELECTORAL_LAYERS) {
        const target = {
          source: layer.id,
          "source-layer": layer.id,
          filter: ["==", ["get", "id"], ""] as maplibregl.FilterSpecification,
        };
        instance.addLayer({
          id: `${layer.id}-hover-fill`,
          type: "fill",
          ...target,
          paint: { "fill-color": HOVER_FILL, "fill-opacity": 0.45 },
          layout: { visibility: "none" },
        });
        instance.addLayer({
          id: `${layer.id}-hover`,
          type: "line",
          ...target,
          paint: { "line-color": HOVER_LINE, "line-width": 2.5 },
          layout: { visibility: "none", "line-join": "round" },
        });
      }
      instance.addSource("points", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
        cluster: true,
        clusterRadius: 40,
        clusterMaxZoom: 13,
      });
      instance.addLayer({
        id: "points-cluster",
        type: "circle",
        source: "points",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": "#682575",
          "circle-opacity": 0.85,
          "circle-radius": ["step", ["get", "point_count"], 14, 10, 18, 100, 24],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2,
        },
      });
      instance.addLayer({
        id: "points-count",
        type: "symbol",
        source: "points",
        filter: ["has", "point_count"],
        layout: { "text-field": ["get", "point_count_abbreviated"], "text-size": 12 },
        paint: { "text-color": "#ffffff" },
      });
      instance.addLayer({
        id: "points-single",
        type: "circle",
        source: "points",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": POINT_COLORS,
          "circle-radius": 7,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2,
        },
      });
      instance.on("click", "points-cluster", (event) => {
        const feature = event.features?.[0];
        const source = instance.getSource("points") as maplibregl.GeoJSONSource;
        const clusterId = feature?.properties?.cluster_id;
        if (feature && clusterId != null) {
          source.getClusterExpansionZoom(clusterId).then((zoom) => {
            const [lng, lat] = (feature.geometry as unknown as { coordinates: [number, number] })
              .coordinates;
            instance.easeTo({ center: [lng, lat], zoom });
          });
        }
      });
      instance.on("click", "points-single", (event) => {
        const properties = event.features?.[0]?.properties;
        if (properties) pointClickRef.current?.(properties);
      });
      for (const layer of ["points-cluster", "points-single"]) {
        instance.on("mouseenter", layer, () => {
          instance.getCanvas().style.cursor = "pointer";
        });
        instance.on("mouseleave", layer, () => {
          instance.getCanvas().style.cursor = "";
        });
      }
      setReady(true);
    });
    instance.on("click", (event: maplibregl.MapMouseEvent) => clickRef.current?.(event.lngLat));
    map.current = instance;
    return () => {
      instance.remove();
      map.current = null;
      setReady(false);
    };
  }, []);

  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready) return;
    for (const layer of ELECTORAL_LAYERS) {
      instance.setLayoutProperty(
        `${layer.id}-line`,
        "visibility",
        visible.includes(layer.id) ? "visible" : "none",
      );
    }
  }, [ready, visible]);

  // Separate from the layers so toggling one does not move the camera back to the node.
  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready) return;
    const source = instance.getSource("highlight") as maplibregl.GeoJSONSource | undefined;
    source?.setData(
      highlight
        ? ({
            type: "Feature",
            geometry: highlight,
            properties: {},
          } as maplibregl.GeoJSONSourceSpecification["data"])
        : { type: "FeatureCollection", features: [] },
    );
    if (bbox && bbox.length === 4) {
      instance.fitBounds(
        [
          [bbox[0] ?? 0, bbox[1] ?? 0],
          [bbox[2] ?? 0, bbox[3] ?? 0],
        ],
        { padding: 32, duration: 0 },
      );
    }
  }, [ready, highlight, bbox]);

  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready) return;
    const source = instance.getSource("points") as maplibregl.GeoJSONSource | undefined;
    const data = points ?? { type: "FeatureCollection", features: [] };
    source?.setData(data as maplibregl.GeoJSONSourceSpecification["data"]);
    if (fitPoints && points?.features.length) {
      const bounds = new maplibregl.LngLatBounds();
      for (const feature of points.features) {
        const [lng, lat] = (feature.geometry as { coordinates: [number, number] }).coordinates;
        bounds.extend([lng, lat]);
      }
      instance.fitBounds(bounds, { padding: 48, maxZoom: 15, duration: 0 });
    }
  }, [ready, points, fitPoints]);

  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready) return;
    for (const layer of ELECTORAL_LAYERS) {
      const active = hovered?.layer === layer.id;
      for (const id of [`${layer.id}-hover-fill`, `${layer.id}-hover`]) {
        instance.setFilter(id, ["==", ["get", "id"], active ? hovered.id : ""]);
        instance.setLayoutProperty(id, "visibility", active ? "visible" : "none");
      }
    }
  }, [ready, hovered]);

  return (
    <section
      ref={container}
      className={className ?? "h-[70vh] w-full rounded-lg border"}
      aria-label="Mapa de geografía electoral"
    />
  );
}
