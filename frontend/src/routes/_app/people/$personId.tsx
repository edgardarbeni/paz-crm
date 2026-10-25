import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import {
  addConsentMutation,
  deletePersonMutation,
  getPersonOptions,
  getPersonQueryKey,
  listConsentsOptions,
  listConsentsQueryKey,
  updatePersonMutation,
} from "@/client/@tanstack/react-query.gen";
import type { PersonOut } from "@/client/types.gen";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CURP_ENTITY_NAMES } from "@/features/people/entities";
import { PersonForm } from "@/features/people/person-form";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";
import { formatDate, formatDateTime, SEX_LABELS } from "@/lib/labels";

export const Route = createFileRoute("/_app/people/$personId")({ component: PersonPage });

function PersonPage() {
  const { personId } = Route.useParams();
  const navigate = useNavigate();
  const can = useCan();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const person = useQuery(getPersonOptions({ path: { person_id: personId } }));
  const update = useMutation({
    ...updatePersonMutation(),
    onSuccess: (data) => {
      queryClient.setQueryData(getPersonQueryKey({ path: { person_id: personId } }), data);
      toast.success("Cambios guardados.");
      for (const warning of data.warnings ?? []) toast.warning(warning);
      setEditing(false);
    },
  });
  const remove = useMutation({
    ...deletePersonMutation(),
    onSuccess: (data) => {
      toast.success(
        `Persona dada de baja. Sus datos se eliminan a partir del ${formatDate(data.purge_after)}.`,
      );
      navigate({ to: "/people" });
    },
  });
  if (person.isError) return <ProblemAlert error={person.error} />;
  const p = person.data;
  if (!p) return <p className="text-muted-foreground">Cargando…</p>;

  return (
    <section className="max-w-4xl">
      <PageHeader
        title={p.full_name}
        description={p.curp ? `CURP ${p.curp}` : "Sin CURP"}
        actions={
          <>
            {p.curp_coherence_overridden ? (
              <Badge variant="destructive">CURP con diferencias autorizadas</Badge>
            ) : null}
            {can(Perm.PERSON_WRITE) && !editing ? (
              <Button onClick={() => setEditing(true)}>Editar</Button>
            ) : null}
            {can(Perm.PERSON_DELETE) ? (
              <ConfirmDialog
                trigger={<Button variant="outline">Dar de baja</Button>}
                title="¿Dar de baja a esta persona?"
                description="Cancelación ARCO: deja de aparecer de inmediato y sus datos personales se eliminan al vencer el plazo de retención. No procede si integra una candidatura vigente."
                confirmLabel="Dar de baja"
                destructive
                onConfirm={() => remove.mutate({ path: { person_id: personId } })}
              />
            ) : null}
          </>
        }
      />
      <div className="space-y-6">
        <ProblemAlert error={remove.error} />
        {editing ? (
          <>
            <PersonForm
              person={p}
              error={update.error}
              onSubmit={(body) => update.mutateAsync({ path: { person_id: personId }, body })}
            />
            <Button variant="ghost" onClick={() => setEditing(false)}>
              Cancelar edición
            </Button>
          </>
        ) : (
          <PersonSummaryCard person={p} />
        )}
        <Consents personId={personId} />
      </div>
    </section>
  );
}

function PersonSummaryCard({ person }: { person: PersonOut }) {
  const address = person.addresses[0];
  const rows: [string, React.ReactNode][] = [
    ["Sexo", person.sex ? SEX_LABELS[person.sex] : "—"],
    ["Nacimiento", formatDate(person.birth_date)],
    ["Entidad de nacimiento", person.birth_entity ? CURP_ENTITY_NAMES[person.birth_entity] : "—"],
    ["Contactos", person.contacts.map((c) => c.value).join(" · ") || "—"],
    [
      "Domicilio",
      address
        ? [
            address.street,
            address.exterior_number,
            address.postal_code && `CP ${address.postal_code}`,
          ]
            .filter(Boolean)
            .join(" ") || "Registrado (datos protegidos)"
        : "—",
    ],
    ["Alta", formatDateTime(person.created_at)],
  ];
  return (
    <Card>
      <CardContent>
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
          {rows.map(([label, value]) => (
            <div key={label}>
              <dt className="text-xs text-muted-foreground">{label}</dt>
              <dd className="text-sm">{value}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}

function Consents({ personId }: { personId: string }) {
  const can = useCan();
  const queryClient = useQueryClient();
  const consents = useQuery(listConsentsOptions({ path: { person_id: personId } }));
  const [version, setVersion] = useState("");
  const [channel, setChannel] = useState<"panel" | "paper" | "web">("paper");
  const add = useMutation({
    ...addConsentMutation(),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: listConsentsQueryKey({ path: { person_id: personId } }),
      });
      setVersion("");
    },
  });
  const CHANNEL = { panel: "Panel", paper: "Papel", web: "Web" };
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Aviso de privacidad</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <ProblemAlert error={consents.error ?? add.error} />
        <ul className="text-sm">
          {consents.data?.length ? (
            consents.data.map((c) => (
              <li key={c.id}>
                Versión {c.notice_version} ·{" "}
                {CHANNEL[c.channel as keyof typeof CHANNEL] ?? c.channel} ·{" "}
                {formatDateTime(c.accepted_at)}
              </li>
            ))
          ) : (
            <li className="text-muted-foreground">Sin aceptaciones registradas.</li>
          )}
        </ul>
        {can(Perm.PERSON_WRITE) ? (
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              add.mutate({
                path: { person_id: personId },
                body: { notice_version: version.trim(), channel },
              });
            }}
          >
            <div className="grid gap-1.5">
              <Label htmlFor="consent-version">Versión del aviso</Label>
              <Input
                id="consent-version"
                value={version}
                onChange={(e) => setVersion(e.target.value)}
                className="w-40"
                required
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="consent-channel">Medio</Label>
              <select
                id="consent-channel"
                value={channel}
                onChange={(e) => setChannel(e.target.value as typeof channel)}
                className="h-8 rounded-lg border border-input bg-transparent px-2 text-sm"
              >
                {Object.entries(CHANNEL).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <Button type="submit" variant="outline" disabled={!version.trim() || add.isPending}>
              Registrar aceptación
            </Button>
          </form>
        ) : null}
      </CardContent>
    </Card>
  );
}
