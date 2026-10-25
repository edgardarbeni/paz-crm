import { client } from "@/client/client.gen";
import type { Problem } from "@/client/types.gen";
import { createAuthFetch, getSession } from "@/lib/auth/session";

/**
 * Configures the generated API client once at startup. Requests are same-origin in every
 * environment (Caddy in front of API and panel); `credentials: "include"` sends the refresh
 * cookie. The bearer token comes from the in-memory session.
 */
export function configureApiClient(
  baseUrl: string = import.meta.env.VITE_API_BASE_URL ?? "",
  fetchImpl?: typeof fetch,
) {
  client.setConfig({
    baseUrl,
    credentials: "include",
    auth: () => getSession().accessToken ?? undefined,
    fetch: createAuthFetch(fetchImpl) as typeof fetch,
  });
}

export interface RuleViolation {
  rule: string;
  severity: "blocking" | "warning";
  message: string;
  formula_id: string | null;
}

export type ProblemWithExtras = Problem & { violations?: RuleViolation[] };

export function isProblem(error: unknown): error is ProblemWithExtras {
  return (
    typeof error === "object" &&
    error !== null &&
    "status" in error &&
    "title" in error &&
    "code" in error
  );
}

/** Human-readable message for any error thrown by the generated client. */
export function problemMessage(error: unknown): string {
  if (isProblem(error)) {
    if (error.errors?.length) {
      return error.errors.map((e) => `${e.field.replace(/^body\./, "")}: ${e.message}`).join(" · ");
    }
    return error.detail ?? error.title;
  }
  if (error instanceof Error) {
    return "No fue posible conectar con el servidor.";
  }
  return "Ocurrió un error inesperado.";
}
