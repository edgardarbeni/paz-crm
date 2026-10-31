import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import {
  closeCoordinationMutation,
  getCoordinationOptions,
  setCoordinationTerritoryMutation,
} from "@/client/@tanstack/react-query.gen";
import type { CoordinationOut } from "@/client/types.gen";
import type { ComboItem } from "@/components/async-combobox";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { COORDINATION_KIND } from "@/features/party-structure/labels";
import { SeatsPanel } from "@/features/party-structure/seats";
import { TerritoryEditor } from "@/features/party-structure/territory-editor";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";
import { formatDate } from "@/lib/labels";

export const Route = createFileRoute("/_app/structure/coordinations/$coordinationId")({
  component: CoordinationPage,
});

function CoordinationPage() {
  const { coordinationId } = Route.useParams();
  const can = useCan();
  const queryClient = useQueryClient();
  const options = getCoordinationOptions({ path: { coordination_id: coordinationId } });
  const coordination = useQuery(options);
  const close = useMutation({
    ...closeCoordinationMutation(),
    onSuccess: (data) => {
      queryClient.setQueryData(options.queryKey, data);
      toast.success("Coordinación cerrada; su territorio queda libre.");
    },
  });
  if (coordination.isError) return <ProblemAlert error={coordination.error} />;
  const c = coordination.data;
  if (!c) return <p className="text-muted-foreground">Cargando…</p>;
  const write = can(Perm.STRUCTURE_COORDINATION_WRITE) && c.status === "active";
  return (
    <section className="max-w-4xl space-y-6">
      <PageHeader
        title={c.name}
        description={`${COORDINATION_KIND[c.kind]} · desde ${formatDate(c.created_on)}`}
        actions={
          c.status === "closed" ? (
            <Badge variant="secondary">Cerrada {formatDate(c.closed_on)}</Badge>
          ) : write ? (
            <ConfirmDialog
              trigger={<Button variant="outline">Cerrar</Button>}
              title="¿Cerrar la coordinación?"
              description="Antes hay que terminar sus nombramientos vigentes. Su territorio queda libre para otra coordinación."
              confirmLabel="Cerrar"
              destructive
              onConfirm={() =>
                close.mutate({
                  path: { coordination_id: c.id },
                  body: { closed_on: new Date().toISOString().slice(0, 10) },
                })
              }
            />
          ) : null
        }
      />
      <ProblemAlert error={close.error} />
      <Card>
        <CardHeader>
          <CardTitle>
            <h2>Territorio</h2>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {write ? (
            <Territory coordination={c} />
          ) : (
            <ul className="flex flex-wrap gap-1 text-xs">
              {c.territory.map((t) => (
                <li key={t.id} className="rounded-full border px-2 py-0.5">
                  {t.label}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>
            <h2>Equipo</h2>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <SeatsPanel bodyId={c.id} dissolved={c.status === "closed"} />
        </CardContent>
      </Card>
    </section>
  );
}

function Territory({ coordination }: { coordination: CoordinationOut }) {
  const queryClient = useQueryClient();
  const initial: ComboItem[] = coordination.territory.map((t) => ({ id: t.id, label: t.label }));
  const [nodes, setNodes] = useState<ComboItem[]>(initial);
  const [on, setOn] = useState(new Date().toISOString().slice(0, 10));
  const save = useMutation({
    ...setCoordinationTerritoryMutation(),
    onSuccess: (data) => {
      queryClient.setQueryData(
        getCoordinationOptions({ path: { coordination_id: coordination.id } }).queryKey,
        data,
      );
      toast.success("Territorio actualizado; el alcance de sus titulares se ajustó.");
    },
  });
  const changed =
    nodes
      .map((n) => n.id)
      .sort()
      .join() !==
    initial
      .map((n) => n.id)
      .sort()
      .join();
  return (
    <form
      className="grid gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate({
          path: { coordination_id: coordination.id },
          body: { node_ids: nodes.map((n) => n.id), on },
        });
      }}
    >
      <ProblemAlert error={save.error} />
      <TerritoryEditor kind={coordination.kind} nodes={nodes} onChange={setNodes} />
      <div className="flex flex-wrap items-end gap-3">
        <div className="grid gap-1.5">
          <Label htmlFor="territory-date">Fecha del cambio</Label>
          <Input
            id="territory-date"
            type="date"
            value={on}
            onChange={(e) => setOn(e.target.value)}
          />
        </div>
        <Button type="submit" disabled={!changed || nodes.length === 0 || save.isPending}>
          Guardar territorio
        </Button>
      </div>
    </form>
  );
}
