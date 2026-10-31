import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { History, KeyRound, UserPlus, UserX } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import {
  appointMutation,
  chooseDerivedSourceMutation,
  endAppointmentMutation,
  getStructureCatalogOptions,
  grantAppointmentAccessMutation,
  listBodyPositionsOptions,
  listPositionAppointmentsOptions,
  revokeAppointmentAccessMutation,
} from "@/client/@tanstack/react-query.gen";
import type { AppointmentOut, SeatOut } from "@/client/types.gen";
import { AsyncCombobox, type ComboItem } from "@/components/async-combobox";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { FormDialog } from "@/components/form-dialog";
import { ProblemAlert } from "@/components/problem-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { SELECT_CLASS } from "@/features/peace-movement/labels";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";
import { formatDate } from "@/lib/labels";
import { searchPeopleItems } from "@/lib/search";
import { APPOINTMENT_KIND, END_REASON } from "./labels";

const today = () => new Date().toISOString().slice(0, 10);

/** The seats of a body or coordination (D-108): holder, period, access and history. Who may
 * appoint is decided by the API (level and scope, D-105); the panel only hides by permission. */
export function SeatsPanel({ bodyId, dissolved }: { bodyId: string; dissolved: boolean }) {
  const can = useCan();
  const seats = useQuery(listBodyPositionsOptions({ path: { body_id: bodyId } }));
  const write = can(Perm.STRUCTURE_APPOINTMENT_WRITE) && !dissolved;
  const grant = can(Perm.STRUCTURE_APPOINTMENT_GRANT_ACCESS);
  if (seats.isError) return <ProblemAlert error={seats.error} />;
  if (!seats.data) return <p className="text-sm text-muted-foreground">Cargando asientos…</p>;
  return (
    <ul className="divide-y rounded-lg border" aria-label="Asientos">
      {seats.data.map((seat) => (
        <SeatRow key={seat.id} bodyId={bodyId} seat={seat} write={write} grant={grant} />
      ))}
    </ul>
  );
}

function seatName(seat: SeatOut): string {
  return seat.region_number
    ? `${seat.position_type.name} ${seat.region_number}`
    : seat.position_type.name;
}

function SeatRow({
  bodyId,
  seat,
  write,
  grant,
}: {
  bodyId: string;
  seat: SeatOut;
  write: boolean;
  grant: boolean;
}) {
  const current = seat.current;
  return (
    <li
      className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm"
      aria-label={seatName(seat)}
    >
      <div className="min-w-56 flex-1">
        <div className="font-medium">{seatName(seat)}</div>
        {seat.is_derived ? (
          <div className="text-muted-foreground">
            {seat.choice_pending ? (
              <Badge variant="secondary">Elección pendiente</Badge>
            ) : seat.derived_holder ? (
              <>
                {seat.derived_holder.full_name}
                <span className="text-xs"> · como {seat.derived_from?.name}</span>
              </>
            ) : (
              "Vacante en el cargo de origen"
            )}
          </div>
        ) : current ? (
          <div>
            <Link
              to="/people/$personId"
              params={{ personId: current.person.id }}
              className="underline-offset-4 hover:underline"
            >
              {current.person.full_name}
            </Link>
            <span className="text-xs text-muted-foreground">
              {" "}
              · {APPOINTMENT_KIND[current.kind]} desde {formatDate(current.starts_on)}
              {current.ends_on ? ` hasta ${formatDate(current.ends_on)}` : ""}
            </span>
          </div>
        ) : (
          <div className="text-muted-foreground">
            Vacante{seat.vacant_since ? ` desde ${formatDate(seat.vacant_since)}` : ""}
          </div>
        )}
      </div>
      {current?.has_access ? <Badge variant="outline">Con acceso</Badge> : null}
      <div className="flex flex-wrap gap-1">
        {seat.is_derived && write ? <ChooseSource bodyId={bodyId} seat={seat} /> : null}
        {!seat.is_derived && !current && write ? <Appoint bodyId={bodyId} seat={seat} /> : null}
        {current && grant && !current.has_access ? (
          <GrantAccess bodyId={bodyId} appointment={current} />
        ) : null}
        {current && grant && current.has_access ? (
          <RevokeAccess bodyId={bodyId} appointment={current} />
        ) : null}
        {current && write ? <EndAppointment bodyId={bodyId} appointment={current} /> : null}
        {!seat.is_derived ? <SeatHistory seat={seat} /> : null}
      </div>
    </li>
  );
}

function useRefresh(bodyId: string) {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: [{ _id: "listBodyPositions" }] });
    queryClient.invalidateQueries({ queryKey: [{ _id: "listPositionAppointments" }] });
    queryClient.invalidateQueries({ queryKey: [{ _id: "listPersonAppointments" }] });
    void bodyId;
  };
}

function Appoint({ bodyId, seat }: { bodyId: string; seat: SeatOut }) {
  const refresh = useRefresh(bodyId);
  const can = useCan();
  const [open, setOpen] = useState(false);
  const [person, setPerson] = useState<ComboItem | null>(null);
  const [kind, setKind] = useState("elected");
  const [startsOn, setStartsOn] = useState(today());
  const [endsOn, setEndsOn] = useState("");
  const [appointedBy, setAppointedBy] = useState("");
  const [agreement, setAgreement] = useState("");
  const [withAccess, setWithAccess] = useState(false);
  const [email, setEmail] = useState("");
  const save = useMutation({
    ...appointMutation(),
    onSuccess: (data) => {
      refresh();
      setOpen(false);
      setPerson(null);
      if (data.access_pending) toast.warning(`Nombrado sin acceso: ${data.access_pending}`);
      else toast.success(`${data.person.full_name} nombrado.`);
    },
  });
  const id = `appoint-${seat.id}`;
  return (
    <FormDialog
      trigger={
        <Button size="sm" variant="outline">
          <UserPlus aria-hidden /> Nombrar
        </Button>
      }
      title={`Nombrar: ${seatName(seat)}`}
      description="El titular es una persona registrada con CURP. Si dejas vacío el fin, se propone con el periodo del cargo."
      open={open}
      onOpenChange={setOpen}
      wide
    >
      <form
        className="grid gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (!person) return;
          save.mutate({
            path: { position_id: seat.id },
            body: {
              person_id: person.id,
              kind: kind as never,
              starts_on: startsOn,
              ends_on: endsOn || null,
              appointed_by: appointedBy.trim() || null,
              agreement_ref: agreement.trim() || null,
              access: withAccess ? { email: email.trim() || null } : null,
            },
          });
        }}
      >
        <ProblemAlert error={save.error} />
        <div className="grid gap-1.5">
          <Label htmlFor={`${id}-person`}>Persona</Label>
          <AsyncCombobox
            id={`${id}-person`}
            label="Persona"
            value={person}
            onChange={setPerson}
            queryKey={["appoint-person"]}
            search={searchPeopleItems}
            placeholder="Nombre o CURP"
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="grid gap-1.5">
            <Label htmlFor={`${id}-kind`}>Tipo</Label>
            <select
              id={`${id}-kind`}
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              className={SELECT_CLASS}
            >
              {Object.entries(APPOINTMENT_KIND).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={`${id}-start`}>Inicio</Label>
            <Input
              id={`${id}-start`}
              type="date"
              value={startsOn}
              onChange={(e) => setStartsOn(e.target.value)}
              required
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={`${id}-end`}>Fin (opcional)</Label>
            <Input
              id={`${id}-end`}
              type="date"
              value={endsOn}
              onChange={(e) => setEndsOn(e.target.value)}
            />
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="grid gap-1.5">
            <Label htmlFor={`${id}-by`}>Órgano que elige o nombra</Label>
            <Input
              id={`${id}-by`}
              value={appointedBy}
              onChange={(e) => setAppointedBy(e.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={`${id}-agreement`}>Acuerdo</Label>
            <Input
              id={`${id}-agreement`}
              value={agreement}
              onChange={(e) => setAgreement(e.target.value)}
            />
          </div>
        </div>
        {can(Perm.STRUCTURE_APPOINTMENT_GRANT_ACCESS) ? (
          <fieldset className="grid gap-2 rounded-lg border p-3">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={withAccess}
                onChange={(e) => setWithAccess(e.target.checked)}
              />
              Dar acceso al sistema (invitación y TOTP obligatorio)
            </label>
            {withAccess ? (
              <div className="grid gap-1.5">
                <Label htmlFor={`${id}-email`}>Correo (si la persona aún no tiene cuenta)</Label>
                <Input
                  id={`${id}-email`}
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
            ) : null}
          </fieldset>
        ) : null}
        <Button type="submit" className="justify-self-start" disabled={!person || save.isPending}>
          Nombrar
        </Button>
      </form>
    </FormDialog>
  );
}

function EndAppointment({ bodyId, appointment }: { bodyId: string; appointment: AppointmentOut }) {
  const refresh = useRefresh(bodyId);
  const [open, setOpen] = useState(false);
  const [endedOn, setEndedOn] = useState(today());
  const [reason, setReason] = useState("resignation");
  const [notes, setNotes] = useState("");
  const save = useMutation({
    ...endAppointmentMutation(),
    onSuccess: () => {
      refresh();
      setOpen(false);
      toast.success("Nombramiento terminado; el asiento queda vacante.");
    },
  });
  const id = `end-${appointment.id}`;
  return (
    <FormDialog
      trigger={
        <Button size="sm" variant="ghost">
          <UserX aria-hidden /> Terminar
        </Button>
      }
      title={`Terminar el nombramiento de ${appointment.person.full_name}`}
      description="Se conserva en el historial; si daba acceso, se retira."
      open={open}
      onOpenChange={setOpen}
    >
      <form
        className="grid gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate({
            path: { appointment_id: appointment.id },
            body: { ended_on: endedOn, reason: reason as never, notes: notes.trim() || null },
          });
        }}
      >
        <ProblemAlert error={save.error} />
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="grid gap-1.5">
            <Label htmlFor={`${id}-date`}>Fecha</Label>
            <Input
              id={`${id}-date`}
              type="date"
              value={endedOn}
              onChange={(e) => setEndedOn(e.target.value)}
              required
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={`${id}-reason`}>Motivo</Label>
            <select
              id={`${id}-reason`}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className={SELECT_CLASS}
            >
              {Object.entries(END_REASON).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor={`${id}-notes`}>Notas</Label>
          <Textarea id={`${id}-notes`} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>
        <Button type="submit" className="justify-self-start" disabled={save.isPending}>
          Terminar
        </Button>
      </form>
    </FormDialog>
  );
}

function GrantAccess({ bodyId, appointment }: { bodyId: string; appointment: AppointmentOut }) {
  const refresh = useRefresh(bodyId);
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const save = useMutation({
    ...grantAppointmentAccessMutation(),
    onSuccess: () => {
      refresh();
      setOpen(false);
      toast.success("Acceso otorgado.");
    },
  });
  return (
    <FormDialog
      trigger={
        <Button size="sm" variant="ghost">
          <KeyRound aria-hidden /> Dar acceso
        </Button>
      }
      title={`Dar acceso a ${appointment.person.full_name}`}
      description="Con el rol del cargo y su territorio como alcance. Se reutiliza su cuenta si ya tiene; si no, se invita al correo. El TOTP es obligatorio."
      open={open}
      onOpenChange={setOpen}
    >
      <form
        className="grid gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate({
            path: { appointment_id: appointment.id },
            body: { email: email.trim() || null },
          });
        }}
      >
        <ProblemAlert error={save.error} />
        <div className="grid gap-1.5">
          <Label htmlFor={`access-${appointment.id}`}>Correo (si aún no tiene cuenta)</Label>
          <Input
            id={`access-${appointment.id}`}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <Button type="submit" className="justify-self-start" disabled={save.isPending}>
          Dar acceso
        </Button>
      </form>
    </FormDialog>
  );
}

function RevokeAccess({ bodyId, appointment }: { bodyId: string; appointment: AppointmentOut }) {
  const refresh = useRefresh(bodyId);
  const revoke = useMutation({
    ...revokeAppointmentAccessMutation(),
    onSuccess: () => {
      refresh();
      toast.success("Acceso retirado; el cargo sigue vigente.");
    },
    onError: () => toast.error("No se pudo retirar el acceso."),
  });
  return (
    <ConfirmDialog
      trigger={
        <Button size="sm" variant="ghost">
          Quitar acceso
        </Button>
      }
      title="¿Quitar el acceso que da este cargo?"
      description="El nombramiento sigue vigente. Si la cuenta se queda sin concesiones, se cierran sus sesiones."
      confirmLabel="Quitar acceso"
      destructive
      onConfirm={() => revoke.mutate({ path: { appointment_id: appointment.id } })}
    />
  );
}

function ChooseSource({ bodyId, seat }: { bodyId: string; seat: SeatOut }) {
  const refresh = useRefresh(bodyId);
  const catalog = useQuery(getStructureCatalogOptions());
  const [open, setOpen] = useState(false);
  const [source, setSource] = useState("");
  const [startsOn, setStartsOn] = useState(today());
  const options =
    catalog.data?.flatMap((body) => body.positions).find((p) => p.id === seat.position_type.id)
      ?.derived_from ?? [];
  const save = useMutation({
    ...chooseDerivedSourceMutation(),
    onSuccess: () => {
      refresh();
      setOpen(false);
      toast.success("Fuente del cargo registrada para el periodo.");
    },
  });
  if (options.length < 2) return null;
  return (
    <FormDialog
      trigger={
        <Button size="sm" variant="outline">
          Elegir para el periodo
        </Button>
      }
      title={`¿Quién ocupa la ${seatName(seat)}?`}
      description="Se elige en cada periodo entre los cargos de origen (D-105)."
      open={open}
      onOpenChange={setOpen}
    >
      <form
        className="grid gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (!source) return;
          save.mutate({
            path: { position_id: seat.id },
            body: { source_position_type_id: source, starts_on: startsOn },
          });
        }}
      >
        <ProblemAlert error={save.error} />
        <select
          aria-label="Cargo de origen"
          value={source}
          onChange={(e) => setSource(e.target.value)}
          className={SELECT_CLASS}
        >
          <option value="">Elige…</option>
          {options.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
        </select>
        <div className="grid gap-1.5">
          <Label htmlFor={`choice-${seat.id}`}>Desde</Label>
          <Input
            id={`choice-${seat.id}`}
            type="date"
            value={startsOn}
            onChange={(e) => setStartsOn(e.target.value)}
          />
        </div>
        <Button type="submit" className="justify-self-start" disabled={!source || save.isPending}>
          Guardar
        </Button>
      </form>
    </FormDialog>
  );
}

function SeatHistory({ seat }: { seat: SeatOut }) {
  const [open, setOpen] = useState(false);
  const history = useQuery({
    ...listPositionAppointmentsOptions({ path: { position_id: seat.id } }),
    enabled: open,
  });
  return (
    <FormDialog
      trigger={
        <Button size="sm" variant="ghost" aria-label={`Historial de ${seatName(seat)}`}>
          <History aria-hidden />
        </Button>
      }
      title={`Historial: ${seatName(seat)}`}
      open={open}
      onOpenChange={setOpen}
      wide
    >
      <ProblemAlert error={history.error} />
      {history.data?.length ? (
        <ul className="divide-y text-sm">
          {history.data.map((a) => (
            <li key={a.id} className="py-2">
              <div className="font-medium">{a.person.full_name}</div>
              <div className="text-muted-foreground">
                {APPOINTMENT_KIND[a.kind]} · {formatDate(a.starts_on)} –{" "}
                {a.ended_on
                  ? `${formatDate(a.ended_on)} (${END_REASON[a.end_reason ?? ""] ?? ""})`
                  : "vigente"}
                {a.agreement_ref ? ` · ${a.agreement_ref}` : ""}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">Sin nombramientos registrados.</p>
      )}
    </FormDialog>
  );
}
