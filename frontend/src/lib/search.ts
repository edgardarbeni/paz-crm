import { searchGeography, searchPeople } from "@/client/sdk.gen";
import type { GeoNodeOut, SearchGeographyData } from "@/client/types.gen";
import type { ComboItem } from "@/components/async-combobox";
import { GEO_LEVEL_LABELS } from "@/lib/labels";

export type GeoSearchLevel = NonNullable<SearchGeographyData["query"]["level"]>[number];

type GeoNodeLike = Pick<GeoNodeOut, "level" | "code" | "key" | "name"> &
  Partial<Pick<GeoNodeOut, "state_name" | "municipality_name">>;

const pad = (code: string, size: number) => code.padStart(size, "0");

/** How a geographic node reads in pickers and tables (D-79): what it is, then its state.
 * "Calvillo · Aguascalientes", "Sección 0338 · Aguascalientes", "Distrito federal 03 · Jalisco". */
export function geoNodeLabel(node: GeoNodeLike): { label: string; hint: string } {
  const state = node.state_name ? ` · ${node.state_name}` : "";
  const where = node.municipality_name ? `${node.municipality_name} · ` : "";
  switch (node.level) {
    case "state":
      return { label: node.name ?? node.key, hint: `Estado · ${node.key}` };
    case "electoral_region":
      return { label: `Circunscripción ${node.code}`, hint: node.key };
    case "federal_district":
    case "local_district":
      return {
        label: `${GEO_LEVEL_LABELS[node.level]} ${pad(node.code, 2)}${state}`,
        hint: `Clave ${node.key}`,
      };
    case "section":
      return { label: `Sección ${pad(node.code, 4)}${state}`, hint: `${where}Clave ${node.key}` };
    default:
      return {
        label: `${node.name ?? "Sin nombre"}${state}`,
        hint: `${GEO_LEVEL_LABELS[node.level]} · ${where}${node.key}`,
      };
  }
}

/** What each geographic picker understands, shown as its search placeholder. */
export const GEO_SEARCH_HINTS: Record<string, string> = {
  state: "Nombre del estado",
  municipality: "Nombre del municipio, con o sin estado",
  federal_district: "Número y estado (p. ej. 3 Jalisco)",
  local_district: "Número y estado (p. ej. 3 Jalisco)",
  section: "Número y estado (p. ej. 338 Aguascalientes)",
  locality: "Nombre de la localidad, con o sin estado",
  neighborhood: "Nombre de la colonia, con o sin estado",
};

/** Autocomplete source for geography: name, number + state, or INE key ("01-0338"). */
export async function searchGeoItems(
  term: string,
  levels?: GeoSearchLevel[],
  options: { stateId?: string | null } = {},
): Promise<ComboItem[]> {
  const { data } = await searchGeography({
    query: { q: term, level: levels, limit: 20, state_id: options.stateId ?? undefined },
    throwOnError: true,
  });
  return data.map((node) => ({ id: node.id, ...geoNodeLabel(node) }));
}

const CURP_PATTERN = /^[A-Z]{4}\d{6}[HMX][A-Z]{5}[0-9A-Z]\d$/i;

/** Autocomplete source for people: name, or exact CURP / phone. */
export async function searchPeopleItems(term: string): Promise<ComboItem[]> {
  const digits = term.replace(/\D/g, "");
  const query = CURP_PATTERN.test(term)
    ? { curp: term.toUpperCase() }
    : digits.length >= 10 && digits.length === term.replace(/[\s()+-]/g, "").length
      ? { phone: digits }
      : { q: term };
  const { data } = await searchPeople({ query: { ...query, limit: 20 }, throwOnError: true });
  return data.items.map((person) => ({
    id: person.id,
    label: person.full_name,
    hint: [person.curp, person.sex].filter(Boolean).join(" · ") || undefined,
  }));
}
