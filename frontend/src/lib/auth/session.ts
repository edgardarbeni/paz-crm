import { refreshSession } from "@/client/sdk.gen";
import type { TokenScope } from "@/client/types.gen";

/**
 * Session state for the panel (D-48): the access token lives only in memory; the refresh
 * token is an httpOnly cookie the browser sends to /api/v1/auth/refresh. Reloading the page
 * restores the session through that refresh.
 */
export interface SessionState {
  accessToken: string | null;
  scope: TokenScope | null;
}

let state: SessionState = { accessToken: null, scope: null };
const listeners = new Set<() => void>();

export function getSession(): SessionState {
  return state;
}

export function setSession(accessToken: string, scope: TokenScope): void {
  state = { accessToken, scope };
  for (const listener of listeners) listener();
}

export function clearSession(): void {
  state = { accessToken: null, scope: null };
  for (const listener of listeners) listener();
}

export function subscribeSession(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

let inflight: Promise<boolean> | null = null;

/** Renews the access token with the refresh cookie. Concurrent callers share one request
 * (refresh tokens rotate: two parallel refreshes would look like reuse and end the session). */
export function refreshAccessToken(): Promise<boolean> {
  inflight ??= (async () => {
    try {
      const { data } = await refreshSession({ fetch: globalThis.fetch.bind(globalThis) });
      if (!data) {
        clearSession();
        return false;
      }
      setSession(data.access_token, data.scope);
      return true;
    } catch {
      clearSession();
      return false;
    } finally {
      inflight = null;
    }
  })();
  return inflight;
}

const NO_RETRY = ["/api/v1/auth/login", "/api/v1/auth/refresh", "/api/v1/auth/mfa/verify"];

/**
 * `fetch` for the generated client: on 401 it refreshes once and retries the request with
 * the new token. Requests are cloned up front because a body can be read only once.
 */
export function createAuthFetch(base: typeof fetch = globalThis.fetch.bind(globalThis)) {
  return async (input: Request): Promise<Response> => {
    const retry = input.clone();
    const response = await base(input);
    const path = new URL(input.url, "http://local").pathname;
    if (response.status !== 401 || NO_RETRY.includes(path) || !state.accessToken) {
      return response;
    }
    if (!(await refreshAccessToken())) {
      onSessionExpired();
      return response;
    }
    retry.headers.set("Authorization", `Bearer ${state.accessToken}`);
    return base(retry);
  };
}

let expiredHandler: () => void = () => {};

export function onSessionExpiredHandler(handler: () => void): void {
  expiredHandler = handler;
}

function onSessionExpired(): void {
  expiredHandler();
}
