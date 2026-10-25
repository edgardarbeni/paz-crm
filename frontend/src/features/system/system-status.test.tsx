import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { jsonResponse, mockApi, renderWithQuery } from "@/test/utils";
import { SystemStatus } from "./system-status";

describe("SystemStatus", () => {
  it("shows each dependency as operating when the API is ready", async () => {
    mockApi((request) => {
      expect(new URL(request.url).pathname).toBe("/ready");
      return jsonResponse({ status: "ok", database: "ok", redis: "ok" });
    });
    renderWithQuery(<SystemStatus />);

    expect(screen.getByText("Verificando…")).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: "Dependencias" });
    expect(list).toHaveTextContent("Base de datos");
    expect(list).toHaveTextContent("Redis");
    expect(screen.getAllByText("Operando")).toHaveLength(2);
  });

  it("shows the Problem Details message when dependencies are down", async () => {
    mockApi(() =>
      jsonResponse(
        {
          type: "urn:pazos:problem:service-unavailable",
          title: "Servicio no disponible",
          status: 503,
          code: "service-unavailable",
          detail: "Dependencias no disponibles: Redis.",
        },
        503,
        "application/problem+json",
      ),
    );
    renderWithQuery(<SystemStatus />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Dependencias no disponibles: Redis.",
    );
  });

  it("shows a connection message on network failures", async () => {
    mockApi(() => {
      throw new TypeError("Failed to fetch");
    });
    renderWithQuery(<SystemStatus />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No fue posible conectar con el servidor.",
    );
  });
});
