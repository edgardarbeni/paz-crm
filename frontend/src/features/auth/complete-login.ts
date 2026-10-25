import type { QueryClient } from "@tanstack/react-query";
import type { TokenScope } from "@/client/types.gen";
import { setSession } from "@/lib/auth/session";

/** Only same-app paths are accepted as post-login destinations (no open redirects). */
export function safeRedirect(target: string | undefined): string {
  return target?.startsWith("/") && !target.startsWith("//") ? target : "/";
}

export function startSession(queryClient: QueryClient, accessToken: string, scope: TokenScope) {
  queryClient.clear();
  setSession(accessToken, scope);
}
