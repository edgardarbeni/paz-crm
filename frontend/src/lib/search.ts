import { searchGeography, searchPeople } from "@/client/sdk.gen";
import type { SearchGeographyData } from "@/client/types.gen";
import type { ComboItem } from "@/components/async-combobox";
import { GEO_LEVEL_LABELS } from "@/lib/labels";

export type GeoSearchLevel = NonNullable<SearchGeographyData["query"]["level"]>[number];

/** Autocomplete source for geography: INE key ("01-0338") or name. */
export async function searchGeoItems(
  term: string,
  levels?: GeoSearchLevel[],
): Promise<ComboItem[]> {
  const { data } = await searchGeography({
    query: { q: term, level: levels, limit: 20 },
    throwOnError: true,
  });
  return data.map((node) => ({
    id: node.id,
    label: node.name ? `${node.key} · ${node.name}` : node.key,
    hint: GEO_LEVEL_LABELS[node.level],
  }));
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
