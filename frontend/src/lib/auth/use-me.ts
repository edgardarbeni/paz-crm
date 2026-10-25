import { useQuery } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";
import { getMeOptions } from "@/client/@tanstack/react-query.gen";
import type { MeResponse } from "@/client/types.gen";
import { hasPermission, type PermCode } from "@/lib/auth/permissions";
import { getSession, subscribeSession } from "@/lib/auth/session";

export function useSession() {
  return useSyncExternalStore(subscribeSession, getSession);
}

export function useMe(): MeResponse | undefined {
  const { accessToken } = useSession();
  return useQuery({ ...getMeOptions(), enabled: !!accessToken, staleTime: 60_000 }).data;
}

/** `can(Perm.X)` for the current user. */
export function useCan(): (code: PermCode) => boolean {
  const me = useMe();
  return (code) => hasPermission(me, code);
}
