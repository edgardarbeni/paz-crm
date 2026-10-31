import { useMutation, useQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import {
  createCoordinationMutation,
  listCoordinationsOptions,
} from "@/client/@tanstack/react-query.gen";
import type { CoordinationOut } from "@/client/types.gen";
import type { ComboItem } from "@/components/async-combobox";
import { type Column, DataTable } from "@/components/data/data-table";
import { useCursorPager } from "@/components/data/use-cursor-pager";
import { FormDialog } from "@/components/form-dialog";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { COORDINATION_KIND } from "@/features/party-structure/labels";
import { TerritoryEditor } from "@/features/party-structure/territory-editor";
import { SELECT_CLASS } from "@/features/peace-movement/labels";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";

const KINDS = ["federal", "local", "sectional"] as const;
type Kind = (typeof KINDS)[number];

export const Route = createFileRoute("/_app/structure/coordinations/")({
  validateSearch: z.object({
    kind: z.enum(KINDS).optional(),
    closed: z.boolean().optional(),
  }),
  component: CoordinationsPage,
});

const columns: Column<CoordinationOut>[] = [
  {
    id: "name",
    header: "Coordinación",
    cell: ({ row }) => <span className="font-medium">{row.original.name}</span>,
  },
  { id: "kind", header: "Tipo", cell: ({ row }) => COORDINATION_KIND[row.original.kind] },
  {
    id: "territory",
    header: "Territorio",
    cell: ({ row }) => `${row.original.territory.length} nodos`,
  },
  {
    id: "status",
    header: "Estatus",
    cell: ({ row }) =>
      row.original.status === "closed" ? <Badge variant="secondary">Cerrada</Badge> : "Vigente",
  },
];

/** Territorial coordinations (D-110): operational structure by grouping territory; a district or
 * section belongs to at most one current coordination of its kind. */
function CoordinationsPage() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const can = useCan();
  const query = {
    ...(search.kind ? { kind: search.kind } : {}),
    ...(search.closed ? { include_closed: true } : {}),
  };
  const { cursor, pager } = useCursorPager(JSON.stringify(query));
  const items = useQuery(listCoordinationsOptions({ query: { ...query, cursor, limit: 50 } }));
  return (
    <section>
      <PageHeader
        title="Coordinaciones territoriales"
        description="Federales, locales y seccionales. Sus titulares con acceso ven exactamente su territorio."
        actions={can(Perm.STRUCTURE_COORDINATION_WRITE) ? <NewCoordination /> : null}
      />
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="grid gap-1.5">
          <Label htmlFor="coordination-kind">Tipo</Label>
          <select
            id="coordination-kind"
            className={SELECT_CLASS}
            value={search.kind ?? ""}
            onChange={(e) =>
              navigate({
                search: (prev) => ({ ...prev, kind: (e.target.value || undefined) as Kind }),
              })
            }
          >
            <option value="">Todas</option>
            {KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {COORDINATION_KIND[kind]}
              </option>
            ))}
          </select>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={!!search.closed}
            onChange={(e) =>
              navigate({ search: (prev) => ({ ...prev, closed: e.target.checked || undefined }) })
            }
          />
          Incluir cerradas
        </label>
      </div>
      <ProblemAlert error={items.error} />
      <DataTable
        caption="Coordinaciones"
        columns={columns}
        data={items.data?.items}
        isLoading={items.isPending}
        getRowId={(row) => row.id}
        pager={pager(items.data)}
        onActivate={(row) =>
          navigate({
            to: "/structure/coordinations/$coordinationId",
            params: { coordinationId: row.id },
          })
        }
        empty="No hay coordinaciones con estos filtros."
      />
    </section>
  );
}

function NewCoordination() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<Kind>("sectional");
  const [name, setName] = useState("");
  const [nodes, setNodes] = useState<ComboItem[]>([]);
  const [createdOn, setCreatedOn] = useState(new Date().toISOString().slice(0, 10));
  const create = useMutation({
    ...createCoordinationMutation(),
    onSuccess: (c) => {
      toast.success(`«${c.name}» creada.`);
      setOpen(false);
      navigate({
        to: "/structure/coordinations/$coordinationId",
        params: { coordinationId: c.id },
      });
    },
  });
  return (
    <FormDialog
      trigger={
        <Button>
          <Plus aria-hidden /> Nueva coordinación
        </Button>
      }
      title="Crear una coordinación territorial"
      description="Las locales y seccionales abarcan un solo estado; las federales de varios estados solo las crea el nivel nacional."
      open={open}
      onOpenChange={setOpen}
      wide
    >
      <form
        className="grid gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate({
            body: {
              kind,
              name: name.trim(),
              node_ids: nodes.map((n) => n.id),
              created_on: createdOn,
            },
          });
        }}
      >
        <ProblemAlert error={create.error} />
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="grid gap-1.5">
            <Label htmlFor="new-coordination-kind">Tipo</Label>
            <select
              id="new-coordination-kind"
              className={SELECT_CLASS}
              value={kind}
              onChange={(e) => {
                setKind(e.target.value as Kind);
                setNodes([]);
              }}
            >
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {COORDINATION_KIND[k]}
                </option>
              ))}
            </select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="new-coordination-name">Nombre</Label>
            <Input
              id="new-coordination-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              minLength={2}
            />
          </div>
        </div>
        <TerritoryEditor kind={kind} nodes={nodes} onChange={setNodes} />
        <div className="grid gap-1.5 sm:max-w-48">
          <Label htmlFor="new-coordination-date">Fecha</Label>
          <Input
            id="new-coordination-date"
            type="date"
            value={createdOn}
            onChange={(e) => setCreatedOn(e.target.value)}
          />
        </div>
        <Button
          type="submit"
          className="justify-self-start"
          disabled={name.trim().length < 2 || nodes.length === 0 || create.isPending}
        >
          Crear
        </Button>
      </form>
    </FormDialog>
  );
}
