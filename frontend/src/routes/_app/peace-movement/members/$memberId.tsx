import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Copy, UserPlus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import {
  changeMemberLevelMutation,
  getMemberHistoryOptions,
  getMemberNetworkOptions,
  getMemberOptions,
  getMemberQueryKey,
  listMemberChildrenOptions,
  memberLeavesMutation,
  reassignMemberMutation,
  rejectMemberMutation,
  validateMemberMutation,
} from "@/client/@tanstack/react-query.gen";
import type { MemberSummary, PeaceMemberOut } from "@/client/types.gen";
import type { ComboItem } from "@/components/async-combobox";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { type Column, DataTable } from "@/components/data/data-table";
import { useCursorPager } from "@/components/data/use-cursor-pager";
import { FormDialog } from "@/components/form-dialog";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { CHANNEL, formatCount, ORIGIN } from "@/features/peace-movement/labels";
import {
  Facts,
  GoalProgress,
  LevelSelect,
  MemberPicker,
  MemberStatusBadge,
  ReasonDialog,
  TrafficLight,
  useLevels,
} from "@/features/peace-movement/shared";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";
import { formatDate, formatDateTime } from "@/lib/labels";

export const Route = createFileRoute("/_app/peace-movement/members/$memberId")({
  component: MemberPage,
});

function MemberPage() {
  const { memberId } = Route.useParams();
  const can = useCan();
  const queryClient = useQueryClient();
  const member = useQuery(getMemberOptions({ path: { member_id: memberId } }));
  const { byId } = useLevels();
  const refresh = (data: PeaceMemberOut) => {
    queryClient.setQueryData(getMemberQueryKey({ path: { member_id: memberId } }), data);
    queryClient.invalidateQueries({ queryKey: [{ _id: "getMemberHistory" }] });
  };
  const validate = useMutation({
    ...validateMemberMutation(),
    onSuccess: (data) => {
      refresh(data);
      toast.success("Inscripción validada.");
    },
  });
  const reject = useMutation({
    ...rejectMemberMutation(),
    onSuccess: (data) => {
      refresh(data);
      toast.success("Inscripción rechazada.");
    },
  });
  const leave = useMutation({
    ...memberLeavesMutation(),
    onSuccess: (data) => {
      refresh(data);
      toast.success("Salida registrada.");
    },
  });

  if (member.isError) return <ProblemAlert error={member.error} />;
  const m = member.data;
  if (!m) return <p className="text-muted-foreground">Cargando…</p>;
  const level = byId.get(m.level_id);
  const pending = m.status === "pending_validation";
  const active = m.status === "active";

  return (
    <section className="max-w-6xl">
      <PageHeader
        title={m.person.full_name}
        description={`${level?.name ?? "Pacificador"} · ${ORIGIN[m.origin] ?? m.origin}`}
        actions={
          <>
            <MemberStatusBadge status={m.status} />
            {pending && can(Perm.PEACE_MEMBER_VALIDATE) ? (
              <>
                <ConfirmDialog
                  trigger={<Button>Validar</Button>}
                  title="¿Validar esta inscripción?"
                  description="Pasa a activo y empieza a contar para las metas de su reclutador."
                  confirmLabel="Validar"
                  onConfirm={() => validate.mutate({ path: { member_id: memberId } })}
                />
                <ReasonDialog
                  trigger={<Button variant="outline">Rechazar</Button>}
                  title="Rechazar inscripción"
                  description="La persona se conserva en el sistema; la inscripción queda rechazada."
                  confirmLabel="Rechazar"
                  destructive
                  error={reject.error}
                  pending={reject.isPending}
                  onConfirm={(reason) =>
                    reject.mutateAsync({ path: { member_id: memberId }, body: { reason } })
                  }
                />
              </>
            ) : null}
            {active && can(Perm.PEACE_MEMBER_WRITE) ? (
              <Button asChild variant="outline">
                <Link to="/peace-movement/members/new" search={{ recruiter: memberId }}>
                  <UserPlus aria-hidden /> Inscribir recluta
                </Link>
              </Button>
            ) : null}
            {(active || pending) && can(Perm.PEACE_MEMBER_WRITE) ? (
              <ChangeLevel member={m} onDone={refresh} />
            ) : null}
            {active && can(Perm.PEACE_MEMBER_REASSIGN) ? (
              <Reassign member={m} onDone={refresh} />
            ) : null}
            {active && can(Perm.PEACE_MEMBER_VALIDATE) ? (
              <ReasonDialog
                trigger={<Button variant="ghost">Registrar salida</Button>}
                title="Registrar que deja el movimiento"
                description="La persona sigue en el sistema y su red conserva a su reclutador."
                confirmLabel="Registrar salida"
                error={leave.error}
                pending={leave.isPending}
                onConfirm={(reason) =>
                  leave.mutateAsync({ path: { member_id: memberId }, body: { reason } })
                }
              />
            ) : null}
          </>
        }
      />
      <ProblemAlert error={validate.error} />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0 space-y-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-2">
              <CardTitle>
                <h2>Avance</h2>
              </CardTitle>
              <TrafficLight light={m.traffic_light} />
            </CardHeader>
            <CardContent className="space-y-4">
              <GoalProgress
                label="Reclutas directos activos"
                current={m.direct.active}
                goal={m.recruit_goal}
                pct={m.progress_pct}
              />
              {m.house_goal ? (
                <GoalProgress
                  label="Casas de Paz consolidadas"
                  current={m.network?.houses_consolidated ?? 0}
                  goal={m.house_goal}
                  pct={m.houses_progress_pct}
                />
              ) : null}
              <p className="text-xs text-muted-foreground">
                La meta es la vigente de su nivel en su estado; solo cuentan los reclutas directos
                activos.
              </p>
            </CardContent>
          </Card>
          <Tabs defaultValue="direct">
            <TabsList>
              <TabsTrigger value="direct">Reclutas directos</TabsTrigger>
              <TabsTrigger value="network">Red a 3 niveles</TabsTrigger>
              <TabsTrigger value="person">Datos personales</TabsTrigger>
              <TabsTrigger value="history">Historial</TabsTrigger>
            </TabsList>
            <TabsContent value="direct">
              <Children memberId={memberId} />
            </TabsContent>
            <TabsContent value="network">
              <Network memberId={memberId} />
            </TabsContent>
            <TabsContent value="person">
              <PersonCard member={m} />
            </TabsContent>
            <TabsContent value="history">
              <History memberId={memberId} />
            </TabsContent>
          </Tabs>
        </div>
        <aside className="space-y-6">
          <NetworkCard member={m} />
          <Card>
            <CardHeader>
              <CardTitle>
                <h2>Inscripción</h2>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Facts
                rows={[
                  [
                    "Reclutador",
                    m.recruited_by ? (
                      <Link
                        key="recruiter"
                        to="/peace-movement/members/$memberId"
                        params={{ memberId: m.recruited_by.id }}
                        className="underline-offset-4 hover:underline"
                      >
                        {m.recruited_by.person.full_name}
                      </Link>
                    ) : (
                      "Raíz de la pirámide"
                    ),
                  ],
                  ["Nivel en la red", m.depth === 0 ? "Raíz" : String(m.depth)],
                  ["Canal", CHANNEL[m.channel] ?? m.channel],
                  ["Inscripción", formatDate(m.enrolled_on)],
                  ["Validación", formatDateTime(m.validated_at)],
                  ...(m.origin_detail
                    ? [["Detalle del origen", m.origin_detail] as [string, string]]
                    : []),
                  ...(m.status_reason ? [["Motivo", m.status_reason] as [string, string]] : []),
                  ...(m.left_on ? [["Salida", formatDate(m.left_on)] as [string, string]] : []),
                ]}
              />
            </CardContent>
          </Card>
          {active ? <ReferralCard member={m} /> : null}
        </aside>
      </div>
    </section>
  );
}

function NetworkCard({ member }: { member: PeaceMemberOut }) {
  const { levels } = useLevels();
  const network = member.network;
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Red</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-3 gap-2 text-center">
          <Stat label="Red activa" value={network?.network_total} />
          <Stat label="Directos" value={member.direct.active} />
          <Stat label="Pendientes" value={member.direct.pending} />
        </div>
        {network ? (
          <>
            <ul className="space-y-1 text-sm">
              {levels.map((level) => (
                <li key={level.id} className="flex justify-between">
                  <span className="text-muted-foreground">{level.name}</span>
                  <span className="tabular-nums">
                    {formatCount(network.network_by_level[level.code] ?? 0)}
                  </span>
                </li>
              ))}
            </ul>
            <p className="text-xs text-muted-foreground">
              Casas acreditadas: {network.houses_consolidated} consolidadas, {network.houses_open}{" "}
              abiertas. Cifras al {formatDateTime(network.computed_at)}.
            </p>
          </>
        ) : (
          <p className="text-xs text-muted-foreground">
            Las cifras de la red aparecen en unos minutos, con el siguiente cálculo de agregados.
          </p>
        )}
        {member.direct.hidden ? (
          <p className="text-xs text-muted-foreground">
            {member.direct.hidden} reclutas directos están fuera de tu alcance (solo en totales).
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: number | null | undefined }) {
  return (
    <div className="rounded-lg bg-muted/50 p-2">
      <div className="text-lg font-semibold tabular-nums">{formatCount(value)}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

function ReferralCard({ member }: { member: PeaceMemberOut }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Enlace de inscripción</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <img
          src={member.referral_qr_svg}
          alt={`QR de inscripción de ${member.person.full_name}`}
          className="mx-auto size-40 rounded-lg bg-white p-1"
        />
        <div className="flex items-center gap-2">
          <code className="min-w-0 flex-1 truncate rounded bg-muted px-2 py-1 text-xs">
            {member.referral_url}
          </code>
          <Button
            size="sm"
            variant="outline"
            aria-label="Copiar enlace"
            onClick={() =>
              navigator.clipboard
                .writeText(member.referral_url)
                .then(() => toast.success("Enlace copiado."))
            }
          >
            <Copy aria-hidden />
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Quien se inscriba con este enlace queda pendiente de validar y como recluta directo.
        </p>
      </CardContent>
    </Card>
  );
}

const childColumns = (byLevel: (id: string) => string): Column<MemberSummary>[] => [
  {
    id: "name",
    header: "Nombre",
    cell: ({ row }) => <span className="font-medium">{row.original.person.full_name}</span>,
  },
  { id: "level", header: "Nivel", cell: ({ row }) => byLevel(row.original.level_id) },
  {
    id: "status",
    header: "Estatus",
    cell: ({ row }) => <MemberStatusBadge status={row.original.status} />,
  },
  {
    id: "enrolled",
    header: "Inscripción",
    sortKey: "enrolled_on",
    cell: ({ row }) => formatDate(row.original.enrolled_on),
  },
];

function Children({ memberId }: { memberId: string }) {
  const navigate = useNavigate();
  const { byId } = useLevels();
  const { cursor, pager } = useCursorPager(memberId);
  const children = useQuery(
    listMemberChildrenOptions({ path: { member_id: memberId }, query: { cursor, limit: 25 } }),
  );
  return (
    <div className="space-y-2">
      <ProblemAlert error={children.error} />
      <DataTable
        caption="Reclutas directos"
        columns={childColumns((id) => byId.get(id)?.name ?? "—")}
        data={children.data?.items}
        isLoading={children.isPending}
        getRowId={(row) => row.id}
        pager={pager(children.data)}
        onActivate={(row) =>
          navigate({ to: "/peace-movement/members/$memberId", params: { memberId: row.id } })
        }
        empty="Aún no tiene reclutas."
      />
      {children.data?.hidden ? (
        <p className="text-xs text-muted-foreground">
          Más {children.data.hidden} fuera de tu alcance, que solo se cuentan.
        </p>
      ) : null}
    </div>
  );
}

function Network({ memberId }: { memberId: string }) {
  const { byId } = useLevels();
  const network = useQuery(
    getMemberNetworkOptions({ path: { member_id: memberId }, query: { max_depth: 3, limit: 200 } }),
  );
  if (network.isError) return <ProblemAlert error={network.error} />;
  if (!network.data) return <p className="text-sm text-muted-foreground">Cargando…</p>;
  const rootDepth = network.data.root.member.depth;
  const byDepth = new Map<number, typeof network.data.items>();
  for (const node of network.data.items) {
    const relative = node.member.depth - rootDepth;
    byDepth.set(relative, [...(byDepth.get(relative) ?? []), node]);
  }
  return (
    <div className="space-y-4">
      {[1, 2, 3].map((depth) => {
        const nodes = byDepth.get(depth) ?? [];
        return (
          <div key={depth}>
            <h3 className="mb-2 text-sm font-semibold">
              {depth === 1 ? "Directos" : `${depth}.º nivel`}{" "}
              <span className="font-normal text-muted-foreground">({nodes.length})</span>
            </h3>
            {nodes.length ? (
              <ul className="grid gap-1 sm:grid-cols-2">
                {nodes.map((node) => (
                  <li key={node.member.id}>
                    <Link
                      to="/peace-movement/members/$memberId"
                      params={{ memberId: node.member.id }}
                      className="flex items-center justify-between gap-2 rounded-lg px-2 py-1 text-sm hover:bg-muted"
                    >
                      <span className="truncate">{node.member.person.full_name}</span>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {byId.get(node.member.level_id)?.name} · red{" "}
                        {formatCount(node.network?.network_total ?? 0)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">Nadie en este nivel.</p>
            )}
          </div>
        );
      })}
      {network.data.has_more ? (
        <p className="text-xs text-muted-foreground">
          Se muestran los primeros 200; abre a un integrante para seguir bajando.
        </p>
      ) : null}
      {network.data.hidden ? (
        <p className="text-xs text-muted-foreground">
          {network.data.hidden} integrantes de estos niveles están fuera de tu alcance.
        </p>
      ) : null}
    </div>
  );
}

function PersonCard({ member }: { member: PeaceMemberOut }) {
  const person = member.person;
  const address = person.addresses[0];
  const intake = member.intake as Record<string, unknown> | null | undefined;
  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-3">
          <Facts
            rows={[
              ["CURP", <code key="curp">{person.curp ?? "—"}</code>],
              ["Contactos", person.contacts.map((c) => c.value).join(" · ") || "—"],
              [
                "Domicilio",
                address
                  ? [address.street, address.exterior_number, address.postal_code]
                      .filter(Boolean)
                      .join(" ") || "Registrado (datos protegidos)"
                  : "—",
              ],
              ["Nacimiento", formatDate(person.birth_date)],
            ]}
          />
          <Link
            to="/people/$personId"
            params={{ personId: person.id }}
            className="text-sm underline-offset-4 hover:underline"
          >
            Ver la ficha de la persona
          </Link>
        </CardContent>
      </Card>
      {intake ? (
        <Card>
          <CardHeader>
            <CardTitle>
              <h3>Lo que envió en la inscripción pública</h3>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p className="text-muted-foreground">
              La persona ya estaba registrada; sus datos no se cambiaron. Compara antes de validar.
            </p>
            <pre className="overflow-x-auto rounded-lg bg-muted p-3 text-xs">
              {JSON.stringify(intake, null, 2)}
            </pre>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function History({ memberId }: { memberId: string }) {
  const { byId } = useLevels();
  const history = useQuery(getMemberHistoryOptions({ path: { member_id: memberId } }));
  if (history.isError) return <ProblemAlert error={history.error} />;
  const data = history.data;
  if (!data) return <p className="text-sm text-muted-foreground">Cargando…</p>;
  const events = [
    ...data.levels.map((change) => ({
      at: change.changed_at,
      text: `Nivel: ${byId.get(change.from_level_id)?.name ?? "?"} → ${byId.get(change.to_level_id)?.name ?? "?"}`,
      reason: change.reason,
    })),
    ...data.recruiters.map((change) => ({
      at: change.changed_at,
      text: `Cambio de reclutador (movió ${change.subtree_size} integrantes con su red)`,
      reason: change.reason,
    })),
  ].sort((a, b) => b.at.localeCompare(a.at));
  return events.length ? (
    <ol className="space-y-3 border-l pl-4">
      {events.map((event) => (
        <li key={`${event.at}-${event.text}`} className="text-sm">
          <div className="text-xs text-muted-foreground">{formatDateTime(event.at)}</div>
          <div>{event.text}</div>
          {event.reason ? <div className="text-muted-foreground">«{event.reason}»</div> : null}
        </li>
      ))}
    </ol>
  ) : (
    <p className="text-sm text-muted-foreground">Sin cambios de nivel ni de reclutador.</p>
  );
}

function ChangeLevel({
  member,
  onDone,
}: {
  member: PeaceMemberOut;
  onDone: (m: PeaceMemberOut) => void;
}) {
  const { levels } = useLevels();
  const [open, setOpen] = useState(false);
  const [levelId, setLevelId] = useState(member.level_id);
  const [reason, setReason] = useState("");
  const change = useMutation({
    ...changeMemberLevelMutation(),
    onSuccess: (data) => {
      onDone(data);
      setOpen(false);
      toast.success("Nivel actualizado.");
    },
  });
  return (
    <FormDialog
      trigger={<Button variant="outline">Cambiar nivel</Button>}
      title="Cambiar nivel de participación"
      description="El nivel es un compromiso de la persona; puede subir o bajar y queda en el historial."
      open={open}
      onOpenChange={setOpen}
    >
      <form
        className="grid gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          change.mutate({
            path: { member_id: member.id },
            body: { level_id: levelId, reason: reason.trim() || null },
          });
        }}
      >
        <ProblemAlert error={change.error} />
        <div className="grid gap-1.5">
          <Label htmlFor="new-level">Nivel</Label>
          <LevelSelect id="new-level" levels={levels} value={levelId} onChange={setLevelId} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="level-reason">Motivo (opcional)</Label>
          <Textarea
            id="level-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </div>
        <Button
          type="submit"
          className="justify-self-start"
          disabled={levelId === member.level_id || change.isPending}
        >
          Guardar
        </Button>
      </form>
    </FormDialog>
  );
}

function Reassign({
  member,
  onDone,
}: {
  member: PeaceMemberOut;
  onDone: (m: PeaceMemberOut) => void;
}) {
  const [open, setOpen] = useState(false);
  const [recruiter, setRecruiter] = useState<ComboItem | null>(null);
  const [reason, setReason] = useState("");
  const reassign = useMutation({
    ...reassignMemberMutation(),
    onSuccess: (data) => {
      onDone(data);
      setOpen(false);
      toast.success("Reclutador cambiado; su red se movió con él.");
    },
  });
  return (
    <FormDialog
      trigger={<Button variant="outline">Cambiar reclutador</Button>}
      title="Cambiar reclutador"
      description="Mueve al pacificador y a toda su red bajo otro reclutador activo. No puede ser alguien de su propia red."
      open={open}
      onOpenChange={setOpen}
    >
      <form
        className="grid gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (!recruiter) return;
          reassign.mutate({
            path: { member_id: member.id },
            body: { recruiter_member_id: recruiter.id, reason: reason.trim() },
          });
        }}
      >
        <ProblemAlert error={reassign.error} />
        <div className="grid gap-1.5">
          <Label htmlFor="new-recruiter">Nuevo reclutador</Label>
          <MemberPicker
            id="new-recruiter"
            label="Nuevo reclutador"
            value={recruiter}
            onChange={setRecruiter}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="reassign-reason">Motivo</Label>
          <Textarea
            id="reassign-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            required
          />
        </div>
        <Button
          type="submit"
          className="justify-self-start"
          disabled={!recruiter || reason.trim().length < 3 || reassign.isPending}
        >
          {reassign.isPending ? "Moviendo…" : "Cambiar reclutador"}
        </Button>
        {member.recruited_by ? (
          <p className="text-xs text-muted-foreground">
            Reclutador actual:{" "}
            <Badge variant="outline">{member.recruited_by.person.full_name}</Badge>
          </p>
        ) : null}
      </form>
    </FormDialog>
  );
}
