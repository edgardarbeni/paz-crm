import { describe, expect, it } from "vitest";
import { client } from "@/client/client.gen";
import { configureApiClient, isProblem, problemMessage } from "./api";
import { createQueryClient } from "./query-client";

const problem = {
  type: "urn:pazos:problem:not-found",
  title: "No encontrado",
  status: 404,
  code: "not-found",
};

describe("api helpers", () => {
  it("configures same-origin requests with credentials", () => {
    configureApiClient("https://panel.test");
    expect(client.getConfig()).toMatchObject({
      baseUrl: "https://panel.test",
      credentials: "include",
    });
  });

  it("recognizes Problem Details", () => {
    expect(isProblem(problem)).toBe(true);
    expect(isProblem({ status: 500 })).toBe(false);
    expect(isProblem(null)).toBe(false);
  });

  it("prefers detail, then title, then generic messages", () => {
    expect(problemMessage({ ...problem, detail: "La sección no existe." })).toBe(
      "La sección no existe.",
    );
    expect(problemMessage(problem)).toBe("No encontrado");
    expect(problemMessage(new TypeError("Failed to fetch"))).toBe(
      "No fue posible conectar con el servidor.",
    );
    expect(problemMessage("boom")).toBe("Ocurrió un error inesperado.");
  });
});

describe("query client retry policy", () => {
  const retry = createQueryClient().getDefaultOptions().queries?.retry as (
    count: number,
    error: unknown,
  ) => boolean;

  it("does not retry client errors", () => {
    expect(retry(0, problem)).toBe(false);
  });

  it("retries server and network errors up to twice", () => {
    expect(retry(0, { ...problem, status: 503 })).toBe(true);
    expect(retry(1, new TypeError("network"))).toBe(true);
    expect(retry(2, new TypeError("network"))).toBe(false);
  });
});
