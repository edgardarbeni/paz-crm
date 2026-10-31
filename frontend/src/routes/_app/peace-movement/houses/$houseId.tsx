import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ImagePlus, Plus, Trash2, UserMinus } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import {
  addHouseMeetingMutation,
  addHouseMemberMutation,
  closePeaceHouseMutation,
  deleteHousePhotoMutation,
  getPeaceHouseOptions,
  getPeaceHouseQueryKey,
  listHouseMeetingsOptions,
  listHouseMembersOptions,
  listHousePhotosOptions,
  reassignHouseCreditMutation,
  recordHouseLocationConsentMutation,
  removeHouseMemberMutation,
  revokeHouseLocationConsentMutation,
  updatePeaceHouseMutation,
  uploadHousePhotoMutation,
} from "@/client/@tanstack/react-query.gen";
import { searchHeldPositions } from "@/client/sdk.gen";
import type { GuestIn, HouseOut } from "@/client/types.gen";
import { AsyncCombobox, type ComboItem } from "@/components/async-combobox";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { FormDialog } from "@/components/form-dialog";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { GeoMap, type PointCollection } from "@/features/geography/geo-map";
import { HOUSE_MEMBER_SOURCE, WEEKDAYS } from "@/features/peace-movement/labels";
import {
  Facts,
  GoalProgress,
  HouseStatusBadge,
  MemberPicker,
  ReasonDialog,
} from "@/features/peace-movement/shared";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";
import { formatDate, formatDateTime } from "@/lib/labels";

export const Route = createFileRoute("/_app/peace-movement/houses/$houseId")({
  component: HousePage,
});

function HousePage() {
  const { houseId } = Route.useParams();
  const can = useCan();
  const queryClient = useQueryClient();
  const house = useQuery(getPeaceHouseOptions({ path: { house_id: houseId } }));
  const update = (data: HouseOut) => {
    queryClient.setQueryData(getPeaceHouseQueryKey({ path: { house_id: houseId } }), data);
    queryClient.invalidateQueries({ queryKey: [{ _id: "listHouseMembers" }] });
  };
  const close = useMutation({
    ...closePeaceHouseMutation(),
    onSuccess: (data) => {
      update(data);
      toast.success("Casa cerrada.");
    },
  });
  if (house.isError) return <ProblemAlert error={house.error} />;
  const h = house.data;
  if (!h) return <p className="text-muted-foreground">Cargando…</p>;
  const current = h.status !== "closed";
  const write = can(Perm.PEACE_HOUSE_WRITE) && current;
  const address = h.address;

  return (
    <section className="max-w-6xl">
      <PageHeader
        title={h.name}
        description={`Abierta el ${formatDate(h.opened_on)}${h.capacity ? ` · cupo ${h.capacity}` : ""}`}
        actions={
          <>
            <HouseStatusBadge status={h.status} />
            {h.needs_reassignment ? (
              <Badge variant="destructive">Sin anfitrión o contacto</Badge>
            ) : null}
            {write ? <EditRoles house={h} onDone={update} /> : null}
            {can(Perm.PEACE_HOUSE_REASSIGN_CREDIT) ? (
              <ReassignCredit house={h} onDone={update} />
            ) : null}
            {write ? (
              <ReasonDialog
                trigger={<Button variant="ghost">Cerrar casa</Button>}
                title="Cerrar la Casa de Paz"
                description="El cierre es definitivo: ya no admite integrantes ni reuniones."
                confirmLabel="Cerrar"
                destructive
                error={close.error}
                pending={close.isPending}
                onConfirm={(reason) =>
                  close.mutateAsync({ path: { house_id: houseId }, body: { reason } })
                }
              />
            ) : null}
          </>
        }
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>
                <h2>Consolidación</h2>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <GoalProgress
                label="Integrantes vigentes"
                current={h.member_count}
                goal={h.member_goal}
                pct={h.progress_pct}
              />
              <p className="text-xs text-muted-foreground">
                {h.first_consolidated_on
                  ? `Se consolidó por primera vez el ${formatDate(h.first_consolidated_on)}.`
                  : "Aún no se ha consolidado."}{" "}
                Si los integrantes bajan de la meta, regresa a «abierta».
              </p>
            </CardContent>
          </Card>
          <Members house={h} editable={write} onChange={() => house.refetch()} />
          <Meetings houseId={houseId} editable={write} />
          <Photos houseId={houseId} editable={can(Perm.PEACE_HOUSE_WRITE)} />
        </div>
        <aside className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>
                <h2>Datos</h2>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Facts
                rows={[
                  ["Anfitrión", memberLink(h.host)],
                  ["Contacto", memberLink(h.contact)],
                  [
                    "Crédito",
                    h.credit_pending ? (
                      <Badge key="credit" variant="secondary">
                        Pendiente de asignar
                      </Badge>
                    ) : h.credited_member_id ? (
                      <Link
                        key="credit"
                        to="/peace-movement/members/$memberId"
                        params={{ memberId: h.credited_member_id }}
                        className="underline-offset-4 hover:underline"
                      >
                        Pacificador acreditado
                      </Link>
                    ) : (
                      (h.credited_position ?? "Cargo de la estructura")
                    ),
                  ],
                  [
                    "Horario",
                    h.schedule.length
                      ? h.schedule
                          .map((s) => `${WEEKDAYS[s.day]} ${s.starts_at}–${s.ends_at}`)
                          .join(" · ")
                      : "—",
                  ],
                  [
                    "Domicilio",
                    address.street
                      ? [address.street, address.exterior_number, address.postal_code]
                          .filter(Boolean)
                          .join(" ")
                      : "Protegido (requiere permiso)",
                  ],
                  [
                    "Punto",
                    address.latitude != null
                      ? `${address.latitude}, ${address.longitude} (exacto)`
                      : `${h.approx_latitude}, ${h.approx_longitude} (aproximado)`,
                  ],
                  ...(h.status_reason
                    ? [["Motivo del cierre", h.status_reason] as [string, string]]
                    : []),
                ]}
              />
            </CardContent>
          </Card>
          <HouseLocationMap
            longitude={address.longitude ?? h.approx_longitude}
            latitude={address.latitude ?? h.approx_latitude}
            status={h.status}
          />
          <LocationConsent house={h} editable={can(Perm.PEACE_HOUSE_WRITE)} onDone={update} />
        </aside>
      </div>
    </section>
  );
}

function HouseLocationMap({
  longitude,
  latitude,
  status,
}: {
  longitude: number;
  latitude: number;
  status: string;
}) {
  const points = useMemo<PointCollection>(
    () => ({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [longitude, latitude] },
          properties: { status },
        },
      ],
    }),
    [longitude, latitude, status],
  );
  return (
    <GeoMap
      visible={["states", "municipalities", "sections"]}
      points={points}
      fitPoints
      className="h-56 w-full rounded-lg border"
    />
  );
}

function memberLink(member: HouseOut["host"]) {
  return member ? (
    <Link
      to="/peace-movement/members/$memberId"
      params={{ memberId: member.id }}
      className="underline-offset-4 hover:underline"
    >
      {member.person.full_name}
    </Link>
  ) : (
    "—"
  );
}

function Members({
  house,
  editable,
  onChange,
}: {
  house: HouseOut;
  editable: boolean;
  onChange: () => void;
}) {
  const queryClient = useQueryClient();
  const members = useQuery(listHouseMembersOptions({ path: { house_id: house.id } }));
  const [picked, setPicked] = useState<ComboItem | null>(null);
  const done = () => {
    queryClient.invalidateQueries({ queryKey: [{ _id: "listHouseMembers" }] });
    onChange();
  };
  const add = useMutation({
    ...addHouseMemberMutation(),
    onSuccess: () => {
      setPicked(null);
      done();
    },
  });
  const remove = useMutation({ ...removeHouseMemberMutation(), onSuccess: done });
  const roles = new Set([house.host?.id, house.contact?.id]);
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Integrantes</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <ProblemAlert error={members.error ?? add.error ?? remove.error} />
        {editable ? (
          <form
            className="flex items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (picked)
                add.mutate({ path: { house_id: house.id }, body: { member_id: picked.id } });
            }}
          >
            <div className="grid flex-1 gap-1.5">
              <Label htmlFor="add-house-member">Asignar pacificador</Label>
              <MemberPicker
                id="add-house-member"
                label="Pacificador"
                value={picked}
                onChange={setPicked}
              />
            </div>
            <Button type="submit" disabled={!picked || add.isPending}>
              <Plus aria-hidden /> Asignar
            </Button>
          </form>
        ) : null}
        <ul className="divide-y">
          {members.data?.map((row) => (
            <li key={row.member.id} className="flex items-center justify-between gap-2 py-2">
              <div className="min-w-0">
                <Link
                  to="/peace-movement/members/$memberId"
                  params={{ memberId: row.member.id }}
                  className="text-sm font-medium underline-offset-4 hover:underline"
                >
                  {row.member.person.full_name}
                </Link>
                <p className="text-xs text-muted-foreground">
                  {HOUSE_MEMBER_SOURCE[row.source] ?? row.source} · desde{" "}
                  {formatDate(row.joined_on)}
                </p>
              </div>
              {editable && !roles.has(row.member.id) ? (
                <ConfirmDialog
                  trigger={
                    <Button size="sm" variant="ghost" aria-label="Quitar de la casa">
                      <UserMinus aria-hidden />
                    </Button>
                  }
                  title={`¿Quitar a ${row.member.person.full_name} de la casa?`}
                  description="Deja de contar como integrante desde hoy."
                  confirmLabel="Quitar"
                  onConfirm={() =>
                    remove.mutate({ path: { house_id: house.id, member_id: row.member.id } })
                  }
                />
              ) : null}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function Meetings({ houseId, editable }: { houseId: string; editable: boolean }) {
  const meetings = useQuery(
    listHouseMeetingsOptions({ path: { house_id: houseId }, query: { limit: 20 } }),
  );
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>
          <h2>Reuniones</h2>
        </CardTitle>
        {editable ? <NewMeeting houseId={houseId} /> : null}
      </CardHeader>
      <CardContent>
        <ProblemAlert error={meetings.error} />
        {meetings.data?.items.length ? (
          <ul className="divide-y">
            {meetings.data.items.map((meeting) => (
              <li key={meeting.id} className="flex justify-between gap-2 py-2 text-sm">
                <span>
                  <span className="font-medium">{meeting.topic}</span>
                  <span className="block text-xs text-muted-foreground">
                    {formatDateTime(meeting.held_at)}
                  </span>
                </span>
                <span className="text-right text-xs text-muted-foreground">
                  {meeting.attendee_count} asistentes
                  {meeting.guest_count ? ` · ${meeting.guest_count} invitados` : ""}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">Sin reuniones registradas.</p>
        )}
      </CardContent>
    </Card>
  );
}

function NewMeeting({ houseId }: { houseId: string }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [topic, setTopic] = useState("");
  const [heldAt, setHeldAt] = useState(() => new Date().toISOString().slice(0, 16));
  const [notes, setNotes] = useState("");
  const [attendees, setAttendees] = useState<ComboItem[]>([]);
  const [picked, setPicked] = useState<ComboItem | null>(null);
  const [guests, setGuests] = useState<(GuestIn & { key: string })[]>([]);
  const add = useMutation({
    ...addHouseMeetingMutation(),
    onSuccess: (meeting) => {
      queryClient.invalidateQueries({ queryKey: [{ _id: "listHouseMeetings" }] });
      toast.success(`Reunión registrada con ${meeting.attendee_count} asistentes.`);
      setOpen(false);
      setTopic("");
      setNotes("");
      setAttendees([]);
      setGuests([]);
    },
  });
  return (
    <FormDialog
      trigger={
        <Button size="sm" variant="outline">
          <Plus aria-hidden /> Registrar reunión
        </Button>
      }
      title="Registrar reunión"
      open={open}
      onOpenChange={setOpen}
      wide
    >
      <form
        className="grid gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          add.mutate({
            path: { house_id: houseId },
            body: {
              topic: topic.trim(),
              held_at: new Date(heldAt).toISOString(),
              notes: notes.trim() || null,
              member_ids: attendees.map((a) => a.id),
              guests: guests
                .filter((g) => g.given_names.trim() && g.paternal_surname.trim())
                .map(({ key: _key, ...guest }) => guest),
            },
          });
        }}
      >
        <ProblemAlert error={add.error} />
        <div className="grid gap-3 md:grid-cols-[2fr_1fr]">
          <div className="grid gap-1.5">
            <Label htmlFor="meeting-topic">Tema</Label>
            <Input
              id="meeting-topic"
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
              required
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="meeting-at">Fecha y hora</Label>
            <Input
              id="meeting-at"
              type="datetime-local"
              value={heldAt}
              onChange={(event) => setHeldAt(event.target.value)}
            />
          </div>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="meeting-member">Asistentes pacificadores</Label>
          <div className="flex gap-2">
            <div className="flex-1">
              <MemberPicker
                id="meeting-member"
                label="Pacificador"
                value={picked}
                onChange={setPicked}
              />
            </div>
            <Button
              type="button"
              variant="outline"
              disabled={!picked}
              onClick={() => {
                if (picked && !attendees.some((a) => a.id === picked.id)) {
                  setAttendees((all) => [...all, picked]);
                }
                setPicked(null);
              }}
            >
              Agregar
            </Button>
          </div>
          <div className="flex flex-wrap gap-1">
            {attendees.map((a) => (
              <Badge key={a.id} variant="secondary" className="gap-1">
                {a.label}
                <button
                  type="button"
                  aria-label={`Quitar a ${a.label}`}
                  onClick={() => setAttendees((all) => all.filter((x) => x.id !== a.id))}
                >
                  ×
                </button>
              </Badge>
            ))}
          </div>
        </div>
        <fieldset className="grid gap-2">
          <legend className="text-sm font-medium">Invitados (aún no son pacificadores)</legend>
          {guests.map((guest, index) => (
            <div key={guest.key} className="grid grid-cols-[1fr_1fr_1fr_auto] gap-2">
              <Input
                aria-label="Nombre"
                placeholder="Nombre"
                value={guest.given_names}
                onChange={(event) =>
                  setGuests((all) =>
                    all.map((g, i) =>
                      i === index ? { ...g, given_names: event.target.value } : g,
                    ),
                  )
                }
              />
              <Input
                aria-label="Apellido paterno"
                placeholder="Apellido"
                value={guest.paternal_surname}
                onChange={(event) =>
                  setGuests((all) =>
                    all.map((g, i) =>
                      i === index ? { ...g, paternal_surname: event.target.value } : g,
                    ),
                  )
                }
              />
              <Input
                aria-label="Celular"
                placeholder="Celular (opcional)"
                inputMode="tel"
                value={guest.mobile ?? ""}
                onChange={(event) =>
                  setGuests((all) =>
                    all.map((g, i) =>
                      i === index ? { ...g, mobile: event.target.value || null } : g,
                    ),
                  )
                }
              />
              <Button
                type="button"
                size="sm"
                variant="ghost"
                aria-label="Quitar invitado"
                onClick={() => setGuests((all) => all.filter((_, i) => i !== index))}
              >
                <Trash2 aria-hidden />
              </Button>
            </div>
          ))}
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="justify-self-start"
            onClick={() =>
              setGuests((all) => [
                ...all,
                { key: crypto.randomUUID(), given_names: "", paternal_surname: "", mobile: null },
              ])
            }
          >
            <Plus aria-hidden /> Agregar invitado
          </Button>
        </fieldset>
        <div className="grid gap-1.5">
          <Label htmlFor="meeting-notes">Notas</Label>
          <Textarea id="meeting-notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>
        <Button
          type="submit"
          className="justify-self-start"
          disabled={topic.trim().length < 2 || add.isPending}
        >
          {add.isPending ? "Guardando…" : "Registrar reunión"}
        </Button>
      </form>
    </FormDialog>
  );
}

function Photos({ houseId, editable }: { houseId: string; editable: boolean }) {
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const photos = useQuery(listHousePhotosOptions({ path: { house_id: houseId } }));
  const refresh = () => queryClient.invalidateQueries({ queryKey: [{ _id: "listHousePhotos" }] });
  const upload = useMutation({
    ...uploadHousePhotoMutation(),
    onSuccess: () => {
      refresh();
      toast.success("Foto subida.");
    },
  });
  const remove = useMutation({ ...deleteHousePhotoMutation(), onSuccess: refresh });
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>
          <h2>Fotos</h2>
        </CardTitle>
        {editable ? (
          <>
            <input
              ref={input}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="sr-only"
              aria-label="Elegir foto"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) upload.mutate({ path: { house_id: houseId }, body: { file } });
                event.target.value = "";
              }}
            />
            <Button
              size="sm"
              variant="outline"
              disabled={upload.isPending}
              onClick={() => input.current?.click()}
            >
              <ImagePlus aria-hidden /> {upload.isPending ? "Subiendo…" : "Subir foto"}
            </Button>
          </>
        ) : null}
      </CardHeader>
      <CardContent>
        <ProblemAlert error={photos.error ?? upload.error ?? remove.error} />
        {photos.data?.length ? (
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {photos.data.map((photo) => (
              <li key={photo.id} className="group relative overflow-hidden rounded-lg border">
                <img
                  src={photo.url}
                  alt={photo.caption ?? "Foto de la casa"}
                  className="aspect-square w-full object-cover"
                  loading="lazy"
                />
                {editable ? (
                  <ConfirmDialog
                    trigger={
                      <Button
                        size="sm"
                        variant="destructive"
                        className="absolute right-1 top-1 opacity-0 group-hover:opacity-100 focus:opacity-100"
                        aria-label="Eliminar foto"
                      >
                        <Trash2 aria-hidden />
                      </Button>
                    }
                    title="¿Eliminar la foto?"
                    description="Se borra del almacenamiento."
                    confirmLabel="Eliminar"
                    destructive
                    onConfirm={() =>
                      remove.mutate({ path: { house_id: houseId, photo_id: photo.id } })
                    }
                  />
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">Sin fotos.</p>
        )}
      </CardContent>
    </Card>
  );
}

function EditRoles({ house, onDone }: { house: HouseOut; onDone: (h: HouseOut) => void }) {
  const [open, setOpen] = useState(false);
  const [host, setHost] = useState<ComboItem | null>(
    house.host ? { id: house.host.id, label: house.host.person.full_name } : null,
  );
  const [contact, setContact] = useState<ComboItem | null>(
    house.contact ? { id: house.contact.id, label: house.contact.person.full_name } : null,
  );
  const save = useMutation({
    ...updatePeaceHouseMutation(),
    onSuccess: (data) => {
      onDone(data);
      setOpen(false);
      toast.success("Casa actualizada.");
    },
  });
  return (
    <FormDialog
      trigger={<Button variant="outline">Anfitrión y contacto</Button>}
      title="Anfitrión y contacto"
      description="Deben ser pacificadores activos; entran como integrantes si aún no lo son."
      open={open}
      onOpenChange={setOpen}
    >
      <form
        className="grid gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate({
            path: { house_id: house.id },
            body: { host_member_id: host?.id ?? null, contact_member_id: contact?.id ?? null },
          });
        }}
      >
        <ProblemAlert error={save.error} />
        <div className="grid gap-1.5">
          <Label htmlFor="role-host">Anfitrión</Label>
          <MemberPicker id="role-host" label="Anfitrión" value={host} onChange={setHost} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="role-contact">Contacto</Label>
          <MemberPicker id="role-contact" label="Contacto" value={contact} onChange={setContact} />
        </div>
        <Button type="submit" className="justify-self-start" disabled={save.isPending}>
          Guardar
        </Button>
      </form>
    </FormDialog>
  );
}

function ReassignCredit({ house, onDone }: { house: HouseOut; onDone: (h: HouseOut) => void }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<"member" | "position">("member");
  const [target, setTarget] = useState<ComboItem | null>(null);
  const [seat, setSeat] = useState<ComboItem | null>(null);
  const [reason, setReason] = useState("");
  const save = useMutation({
    ...reassignHouseCreditMutation(),
    onSuccess: (data) => {
      onDone(data);
      setOpen(false);
      toast.success("Crédito reasignado.");
    },
  });
  const chosen = kind === "member" ? target?.id : seat?.id;
  return (
    <FormDialog
      trigger={<Button variant="outline">Reasignar crédito</Button>}
      title="Reasignar el crédito"
      description="El crédito no cambia solo: va a un pacificador activo de cualquier nivel o a un cargo de la estructura, con motivo."
      open={open}
      onOpenChange={setOpen}
    >
      <form
        className="grid gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (!chosen) return;
          save.mutate({
            path: { house_id: house.id },
            body: {
              ...(kind === "member" ? { member_id: chosen } : { position_id: chosen }),
              reason: reason.trim(),
            },
          });
        }}
      >
        <ProblemAlert error={save.error} />
        <div className="flex gap-2">
          {(["member", "position"] as const).map((option) => (
            <Button
              key={option}
              type="button"
              size="sm"
              variant={kind === option ? "default" : "outline"}
              onClick={() => {
                setKind(option);
                setTarget(null);
                setSeat(null);
              }}
            >
              {option === "member" ? "Pacificador" : "Cargo de la estructura"}
            </Button>
          ))}
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="credit-target">Destinatario</Label>
          {kind === "member" ? (
            <MemberPicker
              id="credit-target"
              label="Pacificador"
              value={target}
              onChange={setTarget}
            />
          ) : (
            <AsyncCombobox
              id="credit-target"
              label="Cargo"
              value={seat}
              onChange={setSeat}
              queryKey={["credit-seat"]}
              placeholder="Nombre del cargo o de su titular"
              search={async (term) => {
                const { data } = await searchHeldPositions({
                  query: { q: term, limit: 20 },
                  throwOnError: true,
                });
                return data.map((p) => ({ id: p.id, label: p.label }));
              }}
            />
          )}
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="credit-reason">Motivo</Label>
          <Textarea
            id="credit-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            required
            minLength={3}
          />
        </div>
        <Button
          type="submit"
          className="justify-self-start"
          disabled={!chosen || reason.trim().length < 3 || save.isPending}
        >
          Reasignar
        </Button>
      </form>
    </FormDialog>
  );
}

function LocationConsent({
  house,
  editable,
  onDone,
}: {
  house: HouseOut;
  editable: boolean;
  onDone: (h: HouseOut) => void;
}) {
  const [evidence, setEvidence] = useState("");
  const record = useMutation({
    ...recordHouseLocationConsentMutation(),
    onSuccess: (data) => {
      onDone(data);
      toast.success("Consentimiento registrado: la ubicación es publicable.");
    },
  });
  const revoke = useMutation({ ...revokeHouseLocationConsentMutation(), onSuccess: onDone });
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Ubicación publicable</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <ProblemAlert error={record.error ?? revoke.error} />
        {house.publishable ? (
          <>
            <p>El anfitrión autorizó publicar la ubicación exacta.</p>
            {editable ? (
              <ConfirmDialog
                trigger={<Button variant="outline">Retirar</Button>}
                title="¿Retirar la ubicación publicable?"
                description="La casa deja de aparecer en salidas públicas; el consentimiento queda en el historial."
                confirmLabel="Retirar"
                onConfirm={() => revoke.mutate({ path: { house_id: house.id } })}
              />
            ) : null}
          </>
        ) : (
          <>
            <p className="text-muted-foreground">
              Sin el consentimiento expreso del anfitrión, la ubicación exacta nunca se publica.
            </p>
            {editable && house.host ? (
              <form
                className="grid gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  record.mutate({
                    path: { house_id: house.id },
                    body: { channel: "paper", evidence_uri: evidence.trim() || null },
                  });
                }}
              >
                <Label htmlFor="location-evidence">Evidencia (formato firmado)</Label>
                <Input
                  id="location-evidence"
                  value={evidence}
                  onChange={(event) => setEvidence(event.target.value)}
                />
                <Button type="submit" variant="outline" disabled={record.isPending}>
                  Registrar consentimiento
                </Button>
              </form>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}
