import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import { enrollMemberMutation, getMemberOptions } from "@/client/@tanstack/react-query.gen";
import { searchPeople } from "@/client/sdk.gen";
import type { EnrollmentIn, PersonCreate } from "@/client/types.gen";
import { AsyncCombobox, type ComboItem } from "@/components/async-combobox";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ORIGIN, SELECT_CLASS } from "@/features/peace-movement/labels";
import {
  HousePicker,
  LevelSelect,
  MemberPicker,
  useLevels,
} from "@/features/peace-movement/shared";
import { PersonForm } from "@/features/people/person-form";

export const Route = createFileRoute("/_app/peace-movement/members/new")({
  validateSearch: z.object({ recruiter: z.string().optional() }),
  component: EnrollPage,
});

type Origin = EnrollmentIn["origin"];

interface Membership {
  levelId: string;
  origin: Origin;
  recruiter: ComboItem | null;
  originDetail: string;
  consentChannel: "panel" | "paper";
  evidenceUri: string;
  house: ComboItem | null;
}

function EnrollPage() {
  const { recruiter: recruiterId } = Route.useSearch();
  const navigate = useNavigate();
  const { levels } = useLevels();
  const presetRecruiter = useQuery({
    ...getMemberOptions({ path: { member_id: recruiterId ?? "" } }),
    enabled: !!recruiterId,
  });
  const [membership, setMembership] = useState<Membership>({
    levelId: "",
    origin: "recruiter",
    recruiter: null,
    originDetail: "",
    consentChannel: "panel",
    evidenceUri: "",
    house: null,
  });
  const [mode, setMode] = useState<"new" | "existing">("new");
  const [existing, setExisting] = useState<ComboItem | null>(null);
  const recruiter =
    membership.recruiter ??
    (presetRecruiter.data
      ? { id: presetRecruiter.data.id, label: presetRecruiter.data.person.full_name }
      : null);
  const levelId = membership.levelId || levels[0]?.id || "";

  const queryClient = useQueryClient();
  const enroll = useMutation({
    ...enrollMemberMutation(),
    onSuccess: (member) => {
      // The recruiter's counters and recruit list changed.
      for (const id of ["getMember", "listMemberChildren", "searchMembers", "getMemberNetwork"]) {
        queryClient.invalidateQueries({ queryKey: [{ _id: id }] });
      }
      toast.success(`${member.person.full_name} quedó inscrito.`);
      navigate({ to: "/peace-movement/members/$memberId", params: { memberId: member.id } });
    },
  });

  function body(person: Partial<Pick<EnrollmentIn, "person" | "person_id">>): EnrollmentIn {
    const withRecruiter = membership.origin === "recruiter";
    return {
      ...person,
      level_id: levelId,
      origin: membership.origin,
      recruiter_member_id: withRecruiter ? (recruiter?.id ?? null) : null,
      origin_detail: membership.originDetail.trim() || null,
      house_id: membership.house?.id ?? null,
      consent: {
        channel: membership.consentChannel,
        evidence_uri: membership.evidenceUri.trim() || null,
      },
    };
  }

  const missingRecruiter = membership.origin === "recruiter" && !recruiter;
  const fields = (
    <MembershipFields
      value={membership}
      recruiter={recruiter}
      levelId={levelId}
      onChange={(patch) => setMembership((current) => ({ ...current, ...patch }))}
    />
  );

  return (
    <section className="max-w-4xl space-y-6">
      <PageHeader
        title="Inscribir pacificador"
        description="Desde el panel la inscripción queda activa. Se exigen CURP, domicilio con sección y la aceptación del aviso de privacidad del Movimiento de Paz."
      />
      <ProblemAlert error={enroll.error} title="No se pudo inscribir" />
      <div className="flex gap-2" role="radiogroup" aria-label="Persona">
        <Button
          variant={mode === "new" ? "default" : "outline"}
          role="radio"
          aria-checked={mode === "new"}
          onClick={() => setMode("new")}
        >
          Persona nueva
        </Button>
        <Button
          variant={mode === "existing" ? "default" : "outline"}
          role="radio"
          aria-checked={mode === "existing"}
          onClick={() => setMode("existing")}
        >
          Ya está registrada
        </Button>
      </div>
      {mode === "new" ? (
        <PersonForm
          error={null}
          submitLabel="Inscribir"
          beforeSubmit={
            <>
              {fields}
              {missingRecruiter ? (
                <Alert>
                  <AlertDescription>Elige al reclutador o cambia el origen.</AlertDescription>
                </Alert>
              ) : null}
            </>
          }
          onSubmit={(person) =>
            missingRecruiter
              ? Promise.reject(new Error("recruiter"))
              : enroll.mutateAsync({ body: body({ person: person as PersonCreate }) })
          }
        />
      ) : (
        <form
          className="grid gap-6"
          onSubmit={(event) => {
            event.preventDefault();
            if (existing && !missingRecruiter) {
              enroll.mutate({ body: body({ person_id: existing.id }) });
            }
          }}
        >
          <Card>
            <CardHeader>
              <CardTitle>
                <h2>Persona</h2>
              </CardTitle>
            </CardHeader>
            <CardContent className="grid gap-1.5">
              <Label htmlFor="existing-person">Buscar por nombre, CURP o teléfono</Label>
              <AsyncCombobox
                id="existing-person"
                label="Persona"
                value={existing}
                onChange={setExisting}
                queryKey={["enroll-person"]}
                placeholder="Nombre, CURP o teléfono"
                search={async (term) => {
                  const query = /^[A-Z]{4}\d{6}/i.test(term)
                    ? { curp: term.toUpperCase() }
                    : /^\d{10,}$/.test(term.replace(/\D/g, "")) && /^[\d\s()+-]+$/.test(term)
                      ? { phone: term.replace(/\D/g, "") }
                      : { q: term };
                  const { data } = await searchPeople({
                    query: { ...query, limit: 20 },
                    throwOnError: true,
                  });
                  return data.items.map((p) => ({
                    id: p.id,
                    label: p.full_name,
                    hint: p.curp ?? "Sin CURP",
                  }));
                }}
              />
              <p className="text-xs text-muted-foreground">
                Debe tener CURP y domicilio con sección; si le faltan, complétalos en su ficha.
              </p>
            </CardContent>
          </Card>
          {fields}
          <Button
            type="submit"
            className="justify-self-start"
            disabled={!existing || missingRecruiter || enroll.isPending}
          >
            {enroll.isPending ? "Inscribiendo…" : "Inscribir"}
          </Button>
        </form>
      )}
    </section>
  );
}

function MembershipFields({
  value,
  recruiter,
  levelId,
  onChange,
}: {
  value: Membership;
  recruiter: ComboItem | null;
  levelId: string;
  onChange: (patch: Partial<Membership>) => void;
}) {
  const { levels } = useLevels();
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Movimiento de Paz</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="grid gap-3 md:grid-cols-2">
          <div className="grid gap-1.5">
            <Label htmlFor="enroll-level">Nivel de participación (compromiso)</Label>
            <LevelSelect
              id="enroll-level"
              levels={levels}
              value={levelId}
              onChange={(level) => onChange({ levelId: level })}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="enroll-origin">Origen</Label>
            <select
              id="enroll-origin"
              className={SELECT_CLASS}
              value={value.origin}
              onChange={(event) => onChange({ origin: event.target.value as Origin })}
            >
              {Object.entries(ORIGIN).map(([origin, label]) => (
                <option key={origin} value={origin}>
                  {label}
                </option>
              ))}
            </select>
          </div>
        </div>
        {value.origin === "recruiter" ? (
          <div className="grid gap-1.5">
            <Label htmlFor="enroll-recruiter">Reclutador (pacificador activo)</Label>
            <MemberPicker
              id="enroll-recruiter"
              label="Reclutador"
              value={recruiter}
              onChange={(item) => onChange({ recruiter: item })}
            />
          </div>
        ) : (
          <div className="grid gap-1.5">
            <Label htmlFor="enroll-detail">Detalle del origen</Label>
            <Input
              id="enroll-detail"
              value={value.originDetail}
              placeholder="Evento, campaña o área de la estructura"
              maxLength={300}
              onChange={(event) => onChange({ originDetail: event.target.value })}
            />
            <p className="text-xs text-muted-foreground">
              Sin reclutador, la persona es raíz de una nueva rama de la pirámide.
            </p>
          </div>
        )}
        <div className="grid gap-1.5">
          <Label htmlFor="enroll-house">Casa de Paz (opcional)</Label>
          <HousePicker
            id="enroll-house"
            label="Casa de Paz"
            value={value.house}
            onChange={(item) => onChange({ house: item })}
          />
        </div>
        <fieldset className="grid gap-3 rounded-lg border p-3">
          <legend className="px-1 text-sm font-medium">Aviso de privacidad del MP</legend>
          <div className="grid gap-3 md:grid-cols-[12rem_1fr]">
            <div className="grid gap-1.5">
              <Label htmlFor="enroll-consent">Se aceptó en</Label>
              <select
                id="enroll-consent"
                className={SELECT_CLASS}
                value={value.consentChannel}
                onChange={(event) =>
                  onChange({ consentChannel: event.target.value as "panel" | "paper" })
                }
              >
                <option value="panel">Panel (en presencia)</option>
                <option value="paper">Papel firmado</option>
              </select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="enroll-evidence">Evidencia (opcional)</Label>
              <Input
                id="enroll-evidence"
                value={value.evidenceUri}
                placeholder="Ubicación del formato firmado"
                maxLength={500}
                onChange={(event) => onChange({ evidenceUri: event.target.value })}
              />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            La afiliación a un movimiento político es un dato sensible: el consentimiento debe ser
            expreso.
          </p>
        </fieldset>
      </CardContent>
    </Card>
  );
}
