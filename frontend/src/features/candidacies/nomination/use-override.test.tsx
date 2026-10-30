import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Override } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { clearSession, setSession } from "@/lib/auth/session";
import { jsonResponse, mockApi, renderWithQuery } from "@/test/utils";
import { useOverride } from "./use-override";

const violation = {
  type: "urn:pazos:problem:rule-violation",
  title: "La operación viola reglas de negocio",
  status: 409,
  code: "rule-violation",
  violations: [
    {
      rule: "unique_person_in_process",
      severity: "blocking",
      message: "La persona ya integra otra fórmula.",
      formula_id: null,
    },
  ],
};

function me(permissions: string[]) {
  return {
    id: "01a17000-0000-7000-8000-000000000001",
    email: "a@example.com",
    full_name: "A",
    status: "active",
    roles: [],
    permissions,
    grants_all: false,
    mfa: { enabled: true, required: true },
    session_id: "01a17000-0000-7000-8000-000000000002",
    scope: "full",
    geo_unrestricted: true,
    grants: [],
  };
}

function Harness({ action }: { action: (override?: Override) => Promise<string> }) {
  const override = useOverride();
  return (
    <>
      <Button onClick={() => override.run(action).catch(() => {})}>Guardar</Button>
      {override.dialog}
    </>
  );
}

afterEach(clearSession);

describe("useOverride", () => {
  it("asks for a reason and retries with the override when the user may accept violations", async () => {
    setSession("token", "full");
    mockApi(() => jsonResponse(me(["candidacies.rule.override"])));
    const action = vi.fn(async (override?: Override) => {
      if (!override) throw violation;
      return "ok";
    });
    renderWithQuery(<Harness action={action} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Guardar" })).toBeEnabled());
    await new Promise((resolve) => setTimeout(resolve, 50)); // profile loaded
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));
    const dialog = await screen.findByRole("dialog", {
      name: "La operación viola reglas bloqueantes",
    });
    expect(dialog).toHaveTextContent("La persona ya integra otra fórmula.");
    await userEvent.type(screen.getByLabelText("Motivo de la excepción"), "Acuerdo de la comisión");
    await userEvent.click(screen.getByRole("button", { name: "Aceptar excepción" }));
    await waitFor(() =>
      expect(action).toHaveBeenLastCalledWith({
        rules: ["unique_person_in_process"],
        reason: "Acuerdo de la comisión",
      }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("surfaces the error to users without the override permission", async () => {
    setSession("token", "full");
    mockApi(() => jsonResponse(me([])));
    const action = vi.fn(async () => {
      throw violation;
    });
    renderWithQuery(<Harness action={action} />);
    await new Promise((resolve) => setTimeout(resolve, 50));
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(action).toHaveBeenCalledOnce());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
