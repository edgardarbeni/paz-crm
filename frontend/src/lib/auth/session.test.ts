import { afterEach, describe, expect, it, vi } from "vitest";
import { client } from "@/client/client.gen";
import {
  clearSession,
  createAuthFetch,
  getSession,
  onSessionExpiredHandler,
  refreshAccessToken,
  setSession,
} from "./session";

const ok = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
const unauthorized = () =>
  new Response(
    JSON.stringify({
      type: "urn:pazos:problem:unauthorized",
      title: "No autenticado",
      status: 401,
      code: "unauthorized",
    }),
    {
      status: 401,
      headers: { "Content-Type": "application/problem+json" },
    },
  );
const refreshed = { access_token: "new-token", expires_in: 900, scope: "full" };

afterEach(() => {
  clearSession();
  onSessionExpiredHandler(() => {});
});

describe("session", () => {
  it("notifies subscribers and clears", () => {
    setSession("abc", "full");
    expect(getSession()).toEqual({ accessToken: "abc", scope: "full" });
    clearSession();
    expect(getSession().accessToken).toBeNull();
  });

  it("shares one refresh between concurrent callers (refresh tokens rotate)", async () => {
    const fetchMock = vi.fn(async () => ok(refreshed));
    client.setConfig({ baseUrl: "http://api.test" });
    vi.stubGlobal("fetch", fetchMock);
    const [a, b] = await Promise.all([refreshAccessToken(), refreshAccessToken()]);
    expect(a && b).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(getSession()).toEqual({ accessToken: "new-token", scope: "full" });
    vi.unstubAllGlobals();
  });

  it("retries a request once with the renewed token after a 401", async () => {
    setSession("expired", "full");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ok(refreshed)),
    );
    client.setConfig({ baseUrl: "http://api.test" });
    const seen: string[] = [];
    const base = vi.fn(async (request: Request) => {
      seen.push(request.headers.get("Authorization") ?? "");
      return seen.length === 1 ? unauthorized() : ok({ fine: true });
    });
    const response = await createAuthFetch(base as unknown as typeof fetch)(
      new Request("http://api.test/api/v1/parties", {
        headers: { Authorization: "Bearer expired" },
      }),
    );
    expect(response.status).toBe(200);
    expect(seen).toEqual(["Bearer expired", "Bearer new-token"]);
    vi.unstubAllGlobals();
  });

  it("gives up and reports the expired session when the refresh fails", async () => {
    setSession("expired", "full");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => unauthorized()),
    );
    client.setConfig({ baseUrl: "http://api.test" });
    const expired = vi.fn();
    onSessionExpiredHandler(expired);
    const base = vi.fn(async () => unauthorized());
    const response = await createAuthFetch(base as unknown as typeof fetch)(
      new Request("http://api.test/api/v1/parties"),
    );
    expect(response.status).toBe(401);
    expect(expired).toHaveBeenCalledOnce();
    expect(getSession().accessToken).toBeNull();
    vi.unstubAllGlobals();
  });

  it("never retries the login endpoints themselves", async () => {
    setSession("token", "full");
    const base = vi.fn(async () => unauthorized());
    await createAuthFetch(base as unknown as typeof fetch)(
      new Request("http://api.test/api/v1/auth/login", { method: "POST" }),
    );
    expect(base).toHaveBeenCalledTimes(1);
  });
});
