import { client } from "@/client/client.gen";
import type { Problem } from "@/client/types.gen";

/**
 * Configures the generated API client once at startup. Requests are same-origin in every
 * environment (Caddy in front of API and panel); `credentials: "include"` sends the refresh
 * cookie that arrives in phase B.
 */
export function configureApiClient(baseUrl: string = import.meta.env.VITE_API_BASE_URL ?? "") {
  client.setConfig({ baseUrl, credentials: "include" });
}

export function isProblem(error: unknown): error is Problem {
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
    return error.detail ?? error.title;
  }
  if (error instanceof Error) {
    return "No fue posible conectar con el servidor.";
  }
  return "Ocurrió un error inesperado.";
}
