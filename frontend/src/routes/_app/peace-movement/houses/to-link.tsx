import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import {
  linkPeaceHouseMutation,
  listHousesToLinkOptions,
  listMyPositionsOptions,
} from "@/client/@tanstack/react-query.gen";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { SELECT_CLASS } from "@/features/peace-movement/labels";
import { HouseStatusBadge } from "@/features/peace-movement/shared";
import { formatDate } from "@/lib/labels";

export const Route = createFileRoute("/_app/peace-movement/houses/to-link")({
  component: HousesToLinkPage,
});

/** Tray of houses to link (D-103): current houses without credit, from anywhere. Linking
 * gives the credit to one of the user's party structure seats; the next holder inherits it. */
function HousesToLinkPage() {
  const queryClient = useQueryClient();
  const houses = useQuery(listHousesToLinkOptions({ query: { limit: 100 } }));
  const mine = useQuery(listMyPositionsOptions());
  const [seat, setSeat] = useState("");
  const link = useMutation({
    ...linkPeaceHouseMutation(),
    onSuccess: (house) => {
      toast.success(`«${house.name}» quedó enlazada a tu cargo.`);
      queryClient.invalidateQueries({ queryKey: [{ _id: "listHousesToLink" }] });
      queryClient.invalidateQueries({ queryKey: [{ _id: "searchPeaceHouses" }] });
    },
  });
  const seats = mine.data ?? [];
  const chosen = seat || (seats.length === 1 ? seats[0]?.id : "") || "";
  const items = houses.data?.items ?? [];
  return (
    <section className="max-w-4xl space-y-4">
      <PageHeader
        title="Casas por enlazar"
        description="Casas vigentes sin crédito, de cualquier lugar. Al enlazarlas, el crédito queda en tu cargo y lo hereda quien lo ocupe después."
      />
      <ProblemAlert error={houses.error ?? mine.error ?? link.error} />
      {mine.isSuccess && seats.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No ocupas ningún cargo de la estructura con acceso: no puedes enlazar casas.
        </p>
      ) : (
        <div className="grid gap-1.5 md:max-w-md">
          <Label htmlFor="link-seat">Enlazar con mi cargo</Label>
          <select
            id="link-seat"
            value={chosen}
            onChange={(e) => setSeat(e.target.value)}
            className={SELECT_CLASS}
          >
            <option value="">Elige uno de tus cargos…</option>
            {seats.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
      )}
      {houses.isPending ? (
        <p className="text-sm text-muted-foreground">Cargando…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No hay casas por enlazar.</p>
      ) : (
        <ul className="divide-y rounded-lg border" aria-label="Casas por enlazar">
          {items.map((house) => (
            <li key={house.id} className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm">
              <Link
                to="/peace-movement/houses/$houseId"
                params={{ houseId: house.id }}
                className="font-medium underline-offset-4 hover:underline"
              >
                {house.name}
              </Link>
              <HouseStatusBadge status={house.status} />
              <span className="text-muted-foreground">
                {house.member_count} integrantes · desde {formatDate(house.opened_on)}
              </span>
              <Button
                size="sm"
                variant="outline"
                className="ml-auto"
                disabled={!chosen || link.isPending}
                onClick={() =>
                  link.mutate({ path: { house_id: house.id }, body: { position_id: chosen } })
                }
              >
                Enlazar
              </Button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
