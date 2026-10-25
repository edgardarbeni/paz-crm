import { useState } from "react";
import type { Pager } from "@/components/data/data-table";

/** Keeps the stack of cursors so "Anterior" works with forward-only cursor pagination.
 * Reset it (by changing `resetKey`) whenever filters or sort change. */
export function useCursorPager(resetKey: string) {
  const [state, setState] = useState<{ key: string; stack: (string | undefined)[] }>({
    key: resetKey,
    stack: [undefined],
  });
  const stack = state.key === resetKey ? state.stack : [undefined];
  const cursor = stack[stack.length - 1];

  function pager(page: { has_more: boolean; next_cursor?: string | null } | undefined): Pager {
    return {
      hasMore: !!page?.has_more,
      canPrev: stack.length > 1,
      page: stack.length,
      next: () => {
        if (page?.next_cursor) setState({ key: resetKey, stack: [...stack, page.next_cursor] });
      },
      prev: () => setState({ key: resetKey, stack: stack.slice(0, -1) }),
    };
  }

  return { cursor, pager };
}
