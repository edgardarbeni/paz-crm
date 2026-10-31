import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import {
  addIncompatibilityMutation,
  createPositionTypeMutation,
  getStructureCatalogOptions,
  listIncompatibilitiesOptions,
  removeIncompatibilityMutation,
} from "@/client/@tanstack/react-query.gen";
import type { BodyTypeOut } from "@/client/types.gen";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { FormDialog } from "@/components/form-dialog";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LEVEL } from "@/features/party-structure/labels";
import { SELECT_CLASS } from "@/features/peace-movement/labels";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";

export const Route = createFileRoute("/_app/structure/catalog")({ component: CatalogPage });

/** Statutory catalog (D-105, D-107): seeded from cargos_paz.md, extendable without migrations. */
function CatalogPage() {
  const can = useCan();
  const catalog = useQuery(getStructureCatalogOptions());
  const manage = can(Perm.STRUCTURE_CATALOG_MANAGE);
  return (
    <section className="max-w-5xl space-y-6">
      <PageHeader
        title="Catálogo estatutario"
        description="Órganos y cargos del estatuto, con su fundamento, órgano que elige y periodo. Los cargos del Presídium se toman de otros cargos."
      />
      <ProblemAlert error={catalog.error} />
      <Incompatibilities manage={manage} />
      {(catalog.data ?? []).map((body) => (
        <Card key={body.id}>
          <CardHeader className="flex flex-row items-start justify-between gap-2">
            <div>
              <CardTitle>
                <h2>{body.name}</h2>
              </CardTitle>
              <p className="text-xs text-muted-foreground">
                {LEVEL[body.territorial_level]}
                {body.statutory_basis ? ` · ${body.statutory_basis}` : ""}
                {body.requires_installation ? " · se instala por acuerdo" : ""}
              </p>
            </div>
            {manage ? <NewPosition body={body} /> : null}
          </CardHeader>
          <CardContent>
            <ul className="divide-y text-sm" aria-label={`Cargos de ${body.name}`}>
              {body.positions.map((p) => (
                <li key={p.id} className="flex flex-wrap items-baseline gap-x-2 py-1.5">
                  <span className="font-medium">{p.name}</span>
                  {p.is_derived ? (
                    <Badge variant="outline">
                      De: {p.derived_from.map((d) => d.name).join(" o ")}
                    </Badge>
                  ) : null}
                  {p.scope_rule === "circumscription" ? (
                    <Badge variant="outline">Una por circunscripción</Badge>
                  ) : null}
                  <span className="text-xs text-muted-foreground">
                    {[
                      p.electing_body,
                      p.term_years ? `${p.term_years} años` : null,
                      p.max_consecutive_terms ? `máx. ${p.max_consecutive_terms} periodos` : null,
                      p.statutory_basis,
                      p.default_role ? `rol: ${p.default_role.name}` : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ))}
    </section>
  );
}

function NewPosition({ body }: { body: BodyTypeOut }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [electing, setElecting] = useState("");
  const [years, setYears] = useState("");
  const [basis, setBasis] = useState("");
  const create = useMutation({
    ...createPositionTypeMutation(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [{ _id: "getStructureCatalog" }] });
      setOpen(false);
      setCode("");
      setName("");
      toast.success("Cargo agregado; sus asientos se crean en los órganos vigentes.");
    },
  });
  const id = `new-position-${body.code}`;
  return (
    <FormDialog
      trigger={
        <Button size="sm" variant="outline">
          <Plus aria-hidden /> Cargo
        </Button>
      }
      title={`Agregar un cargo a ${body.name}`}
      description="Para los «demás cargos que se creen». No se inventan reglas: captura lo que dice el acuerdo."
      open={open}
      onOpenChange={setOpen}
    >
      <form
        className="grid gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate({
            body: {
              body_type_id: body.id,
              code: code.trim(),
              name: name.trim(),
              electing_body: electing.trim() || null,
              term_years: years ? Number(years) : null,
              statutory_basis: basis.trim() || null,
              default_role_id: body.positions.find((p) => p.default_role)?.default_role?.id ?? null,
            },
          });
        }}
      >
        <ProblemAlert error={create.error} />
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="grid gap-1.5">
            <Label htmlFor={`${id}-name`}>Nombre</Label>
            <Input id={`${id}-name`} value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={`${id}-code`}>Clave (minúsculas y _)</Label>
            <Input
              id={`${id}-code`}
              value={code}
              pattern="[a-z0-9_]+"
              onChange={(e) => setCode(e.target.value)}
            />
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="grid gap-1.5 sm:col-span-2">
            <Label htmlFor={`${id}-electing`}>Órgano que elige o nombra</Label>
            <Input
              id={`${id}-electing`}
              value={electing}
              onChange={(e) => setElecting(e.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={`${id}-years`}>Periodo (años)</Label>
            <Input
              id={`${id}-years`}
              type="number"
              min={1}
              value={years}
              onChange={(e) => setYears(e.target.value)}
            />
          </div>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor={`${id}-basis`}>Fundamento</Label>
          <Input id={`${id}-basis`} value={basis} onChange={(e) => setBasis(e.target.value)} />
        </div>
        <Button
          type="submit"
          className="justify-self-start"
          disabled={name.trim().length < 2 || code.trim().length < 2 || create.isPending}
        >
          Agregar
        </Button>
      </form>
    </FormDialog>
  );
}

function Incompatibilities({ manage }: { manage: boolean }) {
  const queryClient = useQueryClient();
  const catalog = useQuery(getStructureCatalogOptions());
  const pairs = useQuery(listIncompatibilitiesOptions());
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: [{ _id: "listIncompatibilities" }] });
  const add = useMutation({
    ...addIncompatibilityMutation(),
    onSuccess: () => {
      refresh();
      setA("");
      setB("");
      toast.success("Incompatibilidad registrada.");
    },
  });
  const remove = useMutation({ ...removeIncompatibilityMutation(), onSuccess: refresh });
  const positions = (catalog.data ?? []).flatMap((body) =>
    body.positions.filter((p) => !p.is_derived).map((p) => ({ ...p, body: body.name })),
  );
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Cargos incompatibles</h2>
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Una misma persona no puede ocupar los dos a la vez. Los define jurídico.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        <ProblemAlert error={pairs.error ?? add.error ?? remove.error} />
        {pairs.data?.length ? (
          <ul className="divide-y text-sm" aria-label="Incompatibilidades">
            {pairs.data.map((pair) => (
              <li key={pair.id} className="flex items-center justify-between gap-2 py-1.5">
                <span>
                  {pair.position_type_a.name} ↔ {pair.position_type_b.name}
                </span>
                {manage ? (
                  <ConfirmDialog
                    trigger={
                      <Button size="icon-sm" variant="ghost" aria-label="Quitar incompatibilidad">
                        <Trash2 aria-hidden />
                      </Button>
                    }
                    title="¿Quitar esta incompatibilidad?"
                    description="Esa persona podrá ocupar los dos cargos a la vez."
                    confirmLabel="Quitar"
                    destructive
                    onConfirm={() => remove.mutate({ path: { incompatibility_id: pair.id } })}
                  />
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">No hay incompatibilidades registradas.</p>
        )}
        {manage ? (
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              add.mutate({ body: { position_type_a_id: a, position_type_b_id: b } });
            }}
          >
            {[
              ["incompatible-a", a, setA],
              ["incompatible-b", b, setB],
            ].map(([id, value, setter]) => (
              <select
                key={id as string}
                aria-label="Cargo"
                className={`${SELECT_CLASS} max-w-80`}
                value={value as string}
                onChange={(e) => (setter as (v: string) => void)(e.target.value)}
              >
                <option value="">Elige un cargo…</option>
                {positions.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.body})
                  </option>
                ))}
              </select>
            ))}
            <Button type="submit" variant="outline" disabled={!a || !b || add.isPending}>
              Registrar
            </Button>
          </form>
        ) : null}
      </CardContent>
    </Card>
  );
}
