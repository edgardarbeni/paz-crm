import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/utils";
import { AsyncCombobox, type ComboItem } from "./async-combobox";

function Harness({ search }: { search: (term: string) => Promise<ComboItem[]> }) {
  const [value, setValue] = useState<ComboItem | null>(null);
  return (
    <AsyncCombobox
      label="Propietaria"
      value={value}
      onChange={setValue}
      queryKey={["t"]}
      search={search}
    />
  );
}

describe("AsyncCombobox", () => {
  it("opens on the first key, searches with the typed text and picks with Enter", async () => {
    const search = vi.fn(async (term: string) => [
      { id: "p1", label: `Ana ${term}`, hint: "CURP" },
    ]);
    renderWithQuery(<Harness search={search} />);
    screen.getByRole("combobox", { name: "Propietaria" }).focus();
    await userEvent.keyboard("an");
    await waitFor(() => expect(search).toHaveBeenCalledWith("an"));
    const option = await screen.findByRole("option", { name: /Ana an/ });
    expect(option).toHaveAttribute("data-selected", "true");
    await userEvent.keyboard("{Enter}");
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: "Propietaria: Ana an" })).toBeInTheDocument(),
    );
    await userEvent.click(screen.getByRole("button", { name: "Quitar Propietaria" }));
    expect(screen.getByRole("combobox", { name: "Propietaria" })).toBeInTheDocument();
  });

  it("does not search below the minimum length", async () => {
    const search = vi.fn(async () => []);
    renderWithQuery(<Harness search={search} />);
    screen.getByRole("combobox", { name: "Propietaria" }).focus();
    await userEvent.keyboard("a");
    await new Promise((resolve) => setTimeout(resolve, 350));
    expect(search).not.toHaveBeenCalled();
  });
});
