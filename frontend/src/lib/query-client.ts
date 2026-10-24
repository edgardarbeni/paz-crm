import { QueryClient } from "@tanstack/react-query";
import { isProblem } from "@/lib/api";

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        // Client errors (4xx) will not succeed on retry; network and 5xx errors may.
        retry: (failureCount, error) =>
          !(isProblem(error) && error.status < 500) && failureCount < 2,
        refetchOnWindowFocus: false,
      },
    },
  });
}
