import { useQuery } from "@tanstack/react-query";
import {
  listOfficeTypesOptions,
  listPartiesOptions,
  listProcessesOptions,
} from "@/client/@tanstack/react-query.gen";

/** Small, rarely-changing catalogs, cached for the session. */
export function useCatalogs() {
  const offices = useQuery({ ...listOfficeTypesOptions(), staleTime: 10 * 60_000 });
  const parties = useQuery({ ...listPartiesOptions(), staleTime: 10 * 60_000 });
  const processes = useQuery({ ...listProcessesOptions(), staleTime: 60_000 });
  return {
    offices: offices.data ?? [],
    parties: parties.data ?? [],
    processes: processes.data ?? [],
    officeById: new Map((offices.data ?? []).map((o) => [o.id, o])),
    partyById: new Map((parties.data ?? []).map((p) => [p.id, p])),
    processById: new Map((processes.data ?? []).map((p) => [p.id, p])),
  };
}
