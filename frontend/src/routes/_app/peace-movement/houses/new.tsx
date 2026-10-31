import { useMutation, useQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { LocateFixed, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { listMyPositionsOptions, openPeaceHouseMutation } from "@/client/@tanstack/react-query.gen";
import type { ScheduleSlot } from "@/client/types.gen";
import type { ComboItem } from "@/components/async-combobox";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { GeoMap, type PointCollection } from "@/features/geography/geo-map";
import { SELECT_CLASS, WEEKDAYS } from "@/features/peace-movement/labels";
import { MemberPicker } from "@/features/peace-movement/shared";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";

export const Route = createFileRoute("/_app/peace-movement/houses/new")({
  component: NewHousePage,
});

type Day = ScheduleSlot["day"];
type Slot = ScheduleSlot & { key: string };

const newSlot = (): Slot => ({
  key: crypto.randomUUID(),
  day: "sat",
  starts_at: "10:00",
  ends_at: "12:00",
});

function NewHousePage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [capacity, setCapacity] = useState("");
  const [address, setAddress] = useState({
    street: "",
    exterior_number: "",
    interior_number: "",
    references: "",
    postal_code: "",
  });
  const [point, setPoint] = useState({ latitude: "", longitude: "" });
  const [locating, setLocating] = useState(false);
  const [schedule, setSchedule] = useState<Slot[]>([newSlot()]);
  const [opener, setOpener] = useState<ComboItem | null>(null);
  const [seat, setSeat] = useState("");
  const can = useCan();
  const myPositions = useQuery({
    ...listMyPositionsOptions(),
    enabled: can(Perm.PEACE_HOUSE_LINK),
  });
  const [host, setHost] = useState<ComboItem | null>(null);
  const [contact, setContact] = useState<ComboItem | null>(null);
  const [extra, setExtra] = useState<(ComboItem | null)[]>([]);

  const open = useMutation({
    ...openPeaceHouseMutation(),
    onSuccess: (house) => {
      toast.success(`Casa «${house.name}» abierta.`);
      navigate({ to: "/peace-movement/houses/$houseId", params: { houseId: house.id } });
    },
  });

  const members = new Set(
    [host, contact, ...extra].filter((item): item is ComboItem => !!item).map((item) => item.id),
  );
  const lat = Number(point.latitude);
  const lon = Number(point.longitude);
  const hasPoint = point.latitude !== "" && point.longitude !== "" && !Number.isNaN(lat + lon);
  const picked = useMemo<PointCollection | null>(
    () =>
      hasPoint
        ? {
            type: "FeatureCollection",
            features: [
              {
                type: "Feature",
                geometry: { type: "Point", coordinates: [lon, lat] },
                properties: { status: "open" },
              },
            ],
          }
        : null,
    [hasPoint, lon, lat],
  );
  const ready =
    name.trim().length >= 2 &&
    address.street.trim() &&
    hasPoint &&
    host &&
    contact &&
    members.size >= 2;

  function locate() {
    if (!navigator.geolocation) return toast.error("Este navegador no da la ubicación.");
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocating(false);
        setPoint({
          latitude: position.coords.latitude.toFixed(6),
          longitude: position.coords.longitude.toFixed(6),
        });
      },
      () => {
        setLocating(false);
        toast.error("No se pudo obtener la ubicación.");
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  }

  return (
    <section className="max-w-4xl">
      <PageHeader
        title="Abrir Casa de Paz"
        description="Se abre con al menos 2 integrantes; el anfitrión y el contacto cuentan. El crédito es de quien la abre: un pacificador de cualquier nivel o uno de tus cargos de la estructura. Sin ninguno, queda en la bandeja de casas por enlazar."
      />
      <form
        className="grid gap-6"
        onSubmit={(event) => {
          event.preventDefault();
          if (!ready || !host || !contact) return;
          open.mutate({
            body: {
              name: name.trim(),
              schedule: schedule.map(({ key: _key, ...slot }) => slot),
              capacity: capacity ? Number(capacity) : null,
              address: {
                street: address.street.trim(),
                exterior_number: address.exterior_number.trim() || null,
                interior_number: address.interior_number.trim() || null,
                references: address.references.trim() || null,
                postal_code: address.postal_code.trim() || null,
                latitude: lat,
                longitude: lon,
              },
              opened_by_member_id: seat ? null : (opener?.id ?? null),
              opened_by_position_id: seat || null,
              host_member_id: host.id,
              contact_member_id: contact.id,
              member_ids: [...members].filter((id) => id !== host.id && id !== contact.id),
            },
          });
        }}
      >
        <ProblemAlert error={open.error} title="No se pudo abrir la casa" />
        <Card>
          <CardHeader>
            <CardTitle>
              <h2>Casa</h2>
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4">
            <div className="grid gap-3 md:grid-cols-[3fr_1fr]">
              <div className="grid gap-1.5">
                <Label htmlFor="house-name">Nombre</Label>
                <Input
                  id="house-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  maxLength={150}
                  required
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="house-capacity">Cupo (personas)</Label>
                <Input
                  id="house-capacity"
                  type="number"
                  min={1}
                  value={capacity}
                  onChange={(event) => setCapacity(event.target.value)}
                />
              </div>
            </div>
            <fieldset className="grid gap-2">
              <legend className="text-sm font-medium">Horario</legend>
              {schedule.map((slot, index) => (
                <div key={slot.key} className="flex flex-wrap items-center gap-2">
                  <select
                    aria-label="Día"
                    className={SELECT_CLASS}
                    value={slot.day}
                    onChange={(event) =>
                      setSchedule((all) =>
                        all.map((s, i) =>
                          i === index ? { ...s, day: event.target.value as Day } : s,
                        ),
                      )
                    }
                  >
                    {Object.entries(WEEKDAYS).map(([day, label]) => (
                      <option key={day} value={day}>
                        {label}
                      </option>
                    ))}
                  </select>
                  <Input
                    aria-label="Desde"
                    type="time"
                    className="w-32"
                    value={slot.starts_at}
                    onChange={(event) =>
                      setSchedule((all) =>
                        all.map((s, i) =>
                          i === index ? { ...s, starts_at: event.target.value } : s,
                        ),
                      )
                    }
                  />
                  <span className="text-sm text-muted-foreground">a</span>
                  <Input
                    aria-label="Hasta"
                    type="time"
                    className="w-32"
                    value={slot.ends_at}
                    onChange={(event) =>
                      setSchedule((all) =>
                        all.map((s, i) =>
                          i === index ? { ...s, ends_at: event.target.value } : s,
                        ),
                      )
                    }
                  />
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    aria-label="Quitar horario"
                    onClick={() => setSchedule((all) => all.filter((_, i) => i !== index))}
                  >
                    <Trash2 aria-hidden />
                  </Button>
                </div>
              ))}
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="justify-self-start"
                onClick={() => setSchedule((all) => [...all, newSlot()])}
              >
                <Plus aria-hidden /> Agregar horario
              </Button>
            </fieldset>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>
              <h2>Ubicación</h2>
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4">
            <p className="text-sm text-muted-foreground">
              La calle y el punto exacto se guardan cifrados. En claro solo queda un punto
              aproximado (unos 100 m) para mapas y estadísticas.
            </p>
            <div className="grid gap-3 md:grid-cols-[2fr_1fr_1fr]">
              {(
                [
                  ["street", "Calle"],
                  ["exterior_number", "Núm. exterior"],
                  ["interior_number", "Núm. interior"],
                ] as const
              ).map(([key, label]) => (
                <div key={key} className="grid gap-1.5">
                  <Label htmlFor={`house-${key}`}>{label}</Label>
                  <Input
                    id={`house-${key}`}
                    value={address[key]}
                    onChange={(event) => setAddress((a) => ({ ...a, [key]: event.target.value }))}
                    required={key === "street"}
                  />
                </div>
              ))}
            </div>
            <div className="grid gap-3 md:grid-cols-[1fr_3fr]">
              <div className="grid gap-1.5">
                <Label htmlFor="house-postal">Código postal</Label>
                <Input
                  id="house-postal"
                  inputMode="numeric"
                  maxLength={5}
                  value={address.postal_code}
                  onChange={(event) =>
                    setAddress((a) => ({ ...a, postal_code: event.target.value }))
                  }
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="house-references">Referencias</Label>
                <Input
                  id="house-references"
                  value={address.references}
                  onChange={(event) =>
                    setAddress((a) => ({ ...a, references: event.target.value }))
                  }
                />
              </div>
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <div className="grid gap-1.5">
                <Label htmlFor="house-lat">Latitud</Label>
                <Input
                  id="house-lat"
                  inputMode="decimal"
                  className="w-40"
                  value={point.latitude}
                  onChange={(event) => setPoint((p) => ({ ...p, latitude: event.target.value }))}
                  placeholder="21.881800"
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="house-lon">Longitud</Label>
                <Input
                  id="house-lon"
                  inputMode="decimal"
                  className="w-40"
                  value={point.longitude}
                  onChange={(event) => setPoint((p) => ({ ...p, longitude: event.target.value }))}
                  placeholder="-102.291600"
                />
              </div>
              <Button type="button" variant="outline" onClick={locate} disabled={locating}>
                <LocateFixed aria-hidden /> {locating ? "Ubicando…" : "Usar mi ubicación"}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Haz clic en el mapa para marcar el punto, o escríbelo. La sección, el municipio y el
              estado se calculan con él.
            </p>
            <GeoMap
              visible={["states", "municipalities", "sections"]}
              points={picked}
              onClick={({ lng, lat: clickedLat }) =>
                setPoint({ latitude: clickedLat.toFixed(6), longitude: lng.toFixed(6) })
              }
              className="h-80 w-full rounded-lg border"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>
              <h2>Personas</h2>
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4">
            {myPositions.data?.length ? (
              <div className="grid gap-1.5 md:max-w-md">
                <Label htmlFor="house-seat">Abrir con uno de mis cargos</Label>
                <select
                  id="house-seat"
                  value={seat}
                  onChange={(e) => {
                    setSeat(e.target.value);
                    if (e.target.value) setOpener(null);
                  }}
                  className={SELECT_CLASS}
                >
                  <option value="">No: la abre un pacificador</option>
                  {myPositions.data.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}
            <div className="grid gap-3 md:grid-cols-3">
              {(
                [
                  ["opener", "Pacificador que la abre (opcional)", opener, setOpener],
                  ["host", "Anfitrión", host, setHost],
                  ["contact", "Contacto responsable", contact, setContact],
                ] as const
              ).map(([key, label, value, setter]) => (
                <div key={key} className="grid gap-1.5">
                  <Label htmlFor={`house-${key}-member`}>{label}</Label>
                  <MemberPicker
                    id={`house-${key}-member`}
                    label={label}
                    value={value}
                    onChange={setter}
                  />
                </div>
              ))}
            </div>
            <fieldset className="grid gap-2">
              <legend className="text-sm font-medium">Más integrantes</legend>
              {extra.map((item, index) => (
                <div key={item?.id ?? `empty-${index}`} className="flex items-center gap-2">
                  <div className="flex-1">
                    <MemberPicker
                      id={`house-extra-${index}`}
                      label={`Integrante ${index + 1}`}
                      value={item}
                      onChange={(next) =>
                        setExtra((all) => all.map((m, i) => (i === index ? next : m)))
                      }
                    />
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    aria-label="Quitar integrante"
                    onClick={() => setExtra((all) => all.filter((_, i) => i !== index))}
                  >
                    <Trash2 aria-hidden />
                  </Button>
                </div>
              ))}
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="justify-self-start"
                onClick={() => setExtra((all) => [...all, null])}
              >
                <Plus aria-hidden /> Agregar integrante
              </Button>
            </fieldset>
            <p className="text-sm">
              Integrantes al abrir: <strong>{members.size}</strong>{" "}
              {members.size < 2 ? (
                <span className="text-muted-foreground">(se necesitan al menos 2)</span>
              ) : null}
            </p>
          </CardContent>
        </Card>
        <Button type="submit" className="justify-self-start" disabled={!ready || open.isPending}>
          {open.isPending ? "Abriendo…" : "Abrir casa"}
        </Button>
      </form>
    </section>
  );
}
