import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { useHotkey } from "./use-hotkey";

function Harness({ onNew, onPalette }: { onNew: () => void; onPalette: () => void }) {
  useHotkey("n", onNew);
  useHotkey("mod+k", onPalette);
  return <input aria-label="campo" />;
}

describe("useHotkey", () => {
  it("fires plain keys only outside fields; mod combos always", async () => {
    const onNew = vi.fn();
    const onPalette = vi.fn();
    render(<Harness onNew={onNew} onPalette={onPalette} />);
    await userEvent.keyboard("n");
    expect(onNew).toHaveBeenCalledOnce();
    await userEvent.click(screen.getByLabelText("campo"));
    await userEvent.keyboard("n");
    expect(onNew).toHaveBeenCalledOnce();
    await userEvent.keyboard("{Control>}k{/Control}");
    expect(onPalette).toHaveBeenCalledOnce();
  });
});
