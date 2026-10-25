import {
  type ColumnDef,
  flexRender,
  type RowData,
  tableFeatures,
  useTable,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight } from "lucide-react";
import { useRef } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const features = tableFeatures({});

export type Column<T extends RowData> = ColumnDef<typeof features, T> & {
  /** Server-side sort key; makes the header a sort toggle. */
  sortKey?: string;
};

export interface Pager {
  hasMore: boolean;
  canPrev: boolean;
  next: () => void;
  prev: () => void;
  page: number;
}

interface DataTableProps<T extends RowData> {
  columns: Column<T>[];
  data: T[] | undefined;
  getRowId: (row: T) => string;
  isLoading?: boolean;
  caption: string;
  pager?: Pager;
  /** "-created_at,name" style sort string. */
  sort?: string;
  onSortChange?: (sort: string) => void;
  /** Click or Enter on a row. */
  onActivate?: (row: T) => void;
  empty?: React.ReactNode;
}

/** Server-driven table: data, sort and pages come from the API (cursor pagination). Rows are
 * reachable with Tab/↑/↓ and open with Enter. */
export function DataTable<T extends RowData>({
  columns,
  data,
  getRowId,
  isLoading,
  caption,
  pager,
  sort,
  onSortChange,
  onActivate,
  empty = "Sin resultados.",
}: DataTableProps<T>) {
  const table = useTable<typeof features, T>({
    features,
    columns,
    data: data ?? [],
    getRowId: (row) => getRowId(row),
  });
  const body = useRef<HTMLTableSectionElement>(null);

  function moveFocus(event: React.KeyboardEvent<HTMLTableRowElement>, row: T) {
    const rows = Array.from(body.current?.querySelectorAll<HTMLElement>("tr[data-row]") ?? []);
    const index = rows.indexOf(event.currentTarget);
    if (event.key === "ArrowDown") {
      event.preventDefault();
      rows[Math.min(index + 1, rows.length - 1)]?.focus();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      rows[Math.max(index - 1, 0)]?.focus();
    } else if (event.key === "Enter" && onActivate) {
      event.preventDefault();
      onActivate(row);
    }
  }

  const sortKey = sort?.replace(/^-/, "");
  const descending = sort?.startsWith("-");

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto rounded-2xl border bg-card shadow-brand">
        <table className="w-full text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead className="bg-secondary/60 text-left">
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id}>
                {group.headers.map((header) => {
                  const column = header.column.columnDef as Column<T>;
                  const active = column.sortKey && column.sortKey === sortKey;
                  const content = flexRender(column.header, header.getContext());
                  return (
                    <th
                      key={header.id}
                      scope="col"
                      className="px-3 py-2.5 text-xs font-bold tracking-wide text-muted-foreground uppercase"
                      aria-sort={active ? (descending ? "descending" : "ascending") : undefined}
                    >
                      {column.sortKey && onSortChange ? (
                        <button
                          type="button"
                          className="inline-flex items-center gap-1 tracking-wide uppercase hover:text-foreground"
                          onClick={() =>
                            onSortChange(
                              active && !descending ? `-${column.sortKey}` : `${column.sortKey}`,
                            )
                          }
                        >
                          {content}
                          {active ? (
                            descending ? (
                              <ArrowDown className="size-3" aria-hidden />
                            ) : (
                              <ArrowUp className="size-3" aria-hidden />
                            )
                          ) : null}
                        </button>
                      ) : (
                        content
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody ref={body}>
            {isLoading && !data ? (
              Array.from({ length: 5 }, (_, i) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: static placeholders
                <tr key={i} className="border-t">
                  <td colSpan={columns.length} className="px-3 py-2">
                    <Skeleton className="h-4 w-full" />
                  </td>
                </tr>
              ))
            ) : table.getRowModel().rows.length === 0 ? (
              <tr className="border-t">
                <td
                  colSpan={columns.length}
                  className="px-3 py-6 text-center text-muted-foreground"
                >
                  {empty}
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  data-row
                  tabIndex={onActivate ? 0 : undefined}
                  onKeyDown={(event) => moveFocus(event, row.original)}
                  onClick={onActivate ? () => onActivate(row.original) : undefined}
                  className={cn(
                    "border-t transition-colors outline-none focus-visible:bg-accent focus-visible:shadow-[inset_3px_0_0_var(--primary)]",
                    onActivate && "cursor-pointer hover:bg-brand-soft/70",
                  )}
                >
                  {row.getAllCells().map((cell) => (
                    <td key={cell.id} className="px-3 py-2 align-top">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {pager && (pager.canPrev || pager.hasMore) ? (
        <nav aria-label="Paginación" className="flex items-center justify-end gap-2 text-sm">
          <span className="text-muted-foreground">Página {pager.page}</span>
          <Button variant="outline" size="sm" onClick={pager.prev} disabled={!pager.canPrev}>
            <ChevronLeft aria-hidden /> Anterior
          </Button>
          <Button variant="outline" size="sm" onClick={pager.next} disabled={!pager.hasMore}>
            Siguiente <ChevronRight aria-hidden />
          </Button>
        </nav>
      ) : null}
    </div>
  );
}
