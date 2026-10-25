import { act, render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { type Column, DataTable } from "./data-table";
import { useCursorPager } from "./use-cursor-pager";

interface Row {
  id: string;
  name: string;
}

const columns: Column<Row>[] = [
  { id: "name", header: "Nombre", sortKey: "name", cell: ({ row }) => row.original.name },
];
const rows: Row[] = [
  { id: "1", name: "Aguascalientes" },
  { id: "2", name: "Calvillo" },
];

describe("DataTable", () => {
  it("renders rows, opens them with Enter and moves with the arrow keys", async () => {
    const onActivate = vi.fn();
    render(
      <DataTable
        caption="Municipios"
        columns={columns}
        data={rows}
        getRowId={(r) => r.id}
        onActivate={onActivate}
      />,
    );
    expect(screen.getByRole("table", { name: "Municipios" })).toBeInTheDocument();
    const [first, second] = screen.getAllByRole("row").slice(1);
    first?.focus();
    await userEvent.keyboard("{ArrowDown}");
    expect(second).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    expect(onActivate).toHaveBeenCalledWith(rows[1]);
    await userEvent.click(screen.getByText("Aguascalientes"));
    expect(onActivate).toHaveBeenCalledWith(rows[0]);
  });

  it("toggles the server sort from the header and exposes aria-sort", async () => {
    const onSortChange = vi.fn();
    const { rerender } = render(
      <DataTable
        caption="t"
        columns={columns}
        data={rows}
        getRowId={(r) => r.id}
        sort="name"
        onSortChange={onSortChange}
      />,
    );
    expect(screen.getByRole("columnheader")).toHaveAttribute("aria-sort", "ascending");
    await userEvent.click(screen.getByRole("button", { name: /Nombre/ }));
    expect(onSortChange).toHaveBeenCalledWith("-name");
    rerender(
      <DataTable
        caption="t"
        columns={columns}
        data={rows}
        getRowId={(r) => r.id}
        sort="-name"
        onSortChange={onSortChange}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /Nombre/ }));
    expect(onSortChange).toHaveBeenLastCalledWith("name");
  });

  it("shows placeholders while loading and the empty message", () => {
    const { rerender } = render(
      <DataTable caption="t" columns={columns} data={undefined} isLoading getRowId={(r) => r.id} />,
    );
    expect(screen.getAllByRole("row")).toHaveLength(6);
    rerender(
      <DataTable
        caption="t"
        columns={columns}
        data={[]}
        getRowId={(r) => r.id}
        empty="Nada por aquí."
      />,
    );
    expect(screen.getByText("Nada por aquí.")).toBeInTheDocument();
  });
});

describe("useCursorPager", () => {
  it("walks forward with cursors, back with the stack, and resets on filter change", () => {
    const { result, rerender } = renderHook(({ key }) => useCursorPager(key), {
      initialProps: { key: "a" },
    });
    expect(result.current.cursor).toBeUndefined();
    act(() => result.current.pager({ has_more: true, next_cursor: "c1" }).next());
    expect(result.current.cursor).toBe("c1");
    const page2 = result.current.pager({ has_more: false, next_cursor: null });
    expect(page2).toMatchObject({ page: 2, canPrev: true, hasMore: false });
    act(() => page2.prev());
    expect(result.current.cursor).toBeUndefined();
    act(() => result.current.pager({ has_more: true, next_cursor: "c1" }).next());
    rerender({ key: "b" });
    expect(result.current.cursor).toBeUndefined();
  });
});
