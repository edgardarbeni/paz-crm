import { useMutation, useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { CheckCircle2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
  getPublicEnrollmentFormOptions,
  publicEnrollMutation,
} from "@/client/@tanstack/react-query.gen";
import type { PublicEnrollmentIn, PublicFormOut } from "@/client/types.gen";
import { PazosLogo } from "@/components/brand/logo";
import { ProblemAlert } from "@/components/problem-alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SELECT_CLASS } from "@/features/peace-movement/labels";
import { type PowChallenge, solveChallenge } from "@/features/peace-movement/pow";
import { normalizeCurp, parseCurp } from "@/features/people/curp";
import { CURP_ENTITY_NAMES } from "@/features/people/entities";

export const Route = createFileRoute("/inscripcion/$code")({ component: PublicEnrollmentPage });

// INE numbers the 32 states in the same order as the RENAPO entity codes (AS = 01 … ZS = 32).
const STATES = Object.values(CURP_ENTITY_NAMES)
  .slice(0, 32)
  .map((name, index) => ({ code: index + 1, name }));

/** Public enrollment through a member's link or QR (D-86, D-98). No session; the browser solves
 * a proof of work in the background while the person fills the form. */
function PublicEnrollmentPage() {
  const { code } = Route.useParams();
  const form = useQuery({
    ...getPublicEnrollmentFormOptions({ path: { referral_code: code } }),
    retry: false,
  });
  const [proof, setProof] = useState<{ challenge: PowChallenge; number: number } | null>(null);
  const [done, setDone] = useState(false);
  const enroll = useMutation({ ...publicEnrollMutation(), onSuccess: () => setDone(true) });

  // Solve the challenge as soon as it arrives; a new form (after an error) brings a new one.
  useEffect(() => {
    const challenge = form.data?.challenge;
    if (!challenge) return;
    const controller = new AbortController();
    setProof(null);
    solveChallenge(challenge, { signal: controller.signal })
      .then((number) => setProof({ challenge, number }))
      .catch(() => {});
    return () => controller.abort();
  }, [form.data?.challenge]);

  return (
    <div className="min-h-screen bg-muted/30">
      <header className="bg-brand-gradient px-4 py-6 text-white">
        <div className="mx-auto flex max-w-2xl items-center justify-between gap-4">
          <PazosLogo className="h-auto w-32" />
          <p className="text-right text-sm font-semibold uppercase tracking-wide">
            Movimiento de Paz
          </p>
        </div>
      </header>
      <main id="contenido" className="mx-auto max-w-2xl p-4 py-8">
        {form.isError ? (
          <Card>
            <CardHeader>
              <CardTitle>
                <h1 className="text-xl font-bold">Este enlace no está disponible</h1>
              </CardTitle>
              <CardDescription>
                Pide a quien te invitó un enlace nuevo. Si el problema sigue, intenta más tarde.
              </CardDescription>
            </CardHeader>
          </Card>
        ) : done ? (
          <Card>
            <CardContent className="space-y-3 py-10 text-center">
              <CheckCircle2 aria-hidden className="mx-auto size-12 text-emerald-600" />
              <h1 className="text-xl font-bold">¡Gracias por sumarte!</h1>
              <p className="text-muted-foreground">
                Recibimos tu inscripción. Una persona del Movimiento de Paz la revisará pronto.
              </p>
            </CardContent>
          </Card>
        ) : form.data ? (
          <EnrollmentForm
            code={code}
            data={form.data}
            proof={proof}
            pending={enroll.isPending}
            error={enroll.error}
            onSubmit={(body) =>
              enroll.mutate(
                { body },
                {
                  onError: () => {
                    setProof(null);
                    form.refetch(); // a used or expired challenge: get a fresh one
                  },
                },
              )
            }
          />
        ) : (
          <p className="text-muted-foreground">Cargando…</p>
        )}
      </main>
    </div>
  );
}

function EnrollmentForm({
  code,
  data,
  proof,
  pending,
  error,
  onSubmit,
}: {
  code: string;
  data: PublicFormOut;
  proof: { challenge: PowChallenge; number: number } | null;
  pending: boolean;
  error: unknown;
  onSubmit: (body: PublicEnrollmentIn) => void;
}) {
  const [values, setValues] = useState({
    given_names: "",
    paternal_surname: "",
    maternal_surname: "",
    curp: "",
    mobile: "",
    email: "",
    street: "",
    exterior_number: "",
    postal_code: "",
    state_code: "",
    section_number: "",
    level_id: data.levels[0]?.id ?? "",
    website: "",
  });
  const [accepts, setAccepts] = useState(false);
  const [showNotice, setShowNotice] = useState(false);
  const firstField = useRef<HTMLInputElement>(null);
  const set =
    (key: keyof typeof values) =>
    (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setValues((v) => ({ ...v, [key]: event.target.value }));
  const curp = parseCurp(values.curp);
  const curpError = values.curp.length >= 18 && !curp.ok ? curp.error : undefined;
  const ready =
    values.given_names.trim() &&
    values.paternal_surname.trim() &&
    curp.ok &&
    values.mobile.replace(/\D/g, "").length >= 10 &&
    values.state_code &&
    values.section_number &&
    accepts;

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h1 className="text-2xl font-extrabold">Súmate al Movimiento de Paz</h1>
        </CardTitle>
        <CardDescription>
          Te invitaron a formar parte de la red de pacificadores. Tus datos son confidenciales.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="grid gap-5"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            if (!ready || !proof) return;
            onSubmit({
              referral_code: code,
              level_id: values.level_id,
              notice_version: data.notice.version,
              accepts_notice: accepts,
              website: values.website || null,
              proof: {
                challenge: proof.challenge.challenge,
                salt: proof.challenge.salt,
                signature: proof.challenge.signature,
                number: proof.number,
              },
              person: {
                given_names: values.given_names.trim(),
                paternal_surname: values.paternal_surname.trim(),
                maternal_surname: values.maternal_surname.trim() || null,
                curp: normalizeCurp(values.curp),
                mobile: values.mobile,
                email: values.email.trim() || null,
                street: values.street.trim() || null,
                exterior_number: values.exterior_number.trim() || null,
                postal_code: values.postal_code.trim() || null,
                state_code: Number(values.state_code),
                section_number: Number(values.section_number),
              },
            });
          }}
        >
          <ProblemAlert error={error} title="No se pudo enviar" />
          <fieldset className="grid gap-3">
            <legend className="mb-1 text-sm font-semibold">Tus datos</legend>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field id="pub-names" label="Nombre(s)">
                <Input
                  id="pub-names"
                  ref={firstField}
                  autoComplete="given-name"
                  value={values.given_names}
                  onChange={set("given_names")}
                  required
                />
              </Field>
              <Field id="pub-paternal" label="Primer apellido">
                <Input
                  id="pub-paternal"
                  autoComplete="family-name"
                  value={values.paternal_surname}
                  onChange={set("paternal_surname")}
                  required
                />
              </Field>
              <Field id="pub-maternal" label="Segundo apellido">
                <Input
                  id="pub-maternal"
                  value={values.maternal_surname}
                  onChange={set("maternal_surname")}
                />
              </Field>
            </div>
            <Field id="pub-curp" label="CURP" error={curpError}>
              <Input
                id="pub-curp"
                value={values.curp}
                maxLength={18}
                autoCapitalize="characters"
                className="uppercase"
                aria-invalid={!!curpError}
                onChange={set("curp")}
                required
              />
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field id="pub-mobile" label="Celular (10 dígitos)">
                <Input
                  id="pub-mobile"
                  type="tel"
                  autoComplete="tel"
                  value={values.mobile}
                  onChange={set("mobile")}
                  required
                />
              </Field>
              <Field id="pub-email" label="Correo (opcional)">
                <Input
                  id="pub-email"
                  type="email"
                  autoComplete="email"
                  value={values.email}
                  onChange={set("email")}
                />
              </Field>
            </div>
          </fieldset>
          <fieldset className="grid gap-3">
            <legend className="mb-1 text-sm font-semibold">Dónde vives</legend>
            <p className="-mt-1 text-xs text-muted-foreground">
              La entidad y la sección vienen en tu credencial para votar.
            </p>
            <div className="grid gap-3 sm:grid-cols-[2fr_1fr]">
              <Field id="pub-state" label="Entidad">
                <select
                  id="pub-state"
                  className={`${SELECT_CLASS} h-9`}
                  value={values.state_code}
                  onChange={set("state_code")}
                  required
                >
                  <option value="">Elige tu estado</option>
                  {STATES.map((state) => (
                    <option key={state.code} value={state.code}>
                      {state.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field id="pub-section" label="Sección">
                <Input
                  id="pub-section"
                  inputMode="numeric"
                  maxLength={4}
                  value={values.section_number}
                  onChange={set("section_number")}
                  required
                />
              </Field>
            </div>
            <div className="grid gap-3 sm:grid-cols-[2fr_1fr_1fr]">
              <Field id="pub-street" label="Calle (opcional)">
                <Input
                  id="pub-street"
                  autoComplete="address-line1"
                  value={values.street}
                  onChange={set("street")}
                />
              </Field>
              <Field id="pub-number" label="Número">
                <Input
                  id="pub-number"
                  value={values.exterior_number}
                  onChange={set("exterior_number")}
                />
              </Field>
              <Field id="pub-postal" label="Código postal">
                <Input
                  id="pub-postal"
                  inputMode="numeric"
                  maxLength={5}
                  autoComplete="postal-code"
                  value={values.postal_code}
                  onChange={set("postal_code")}
                />
              </Field>
            </div>
          </fieldset>
          <fieldset className="grid gap-2">
            <legend className="mb-1 text-sm font-semibold">
              ¿Con cuántas personas te comprometes?
            </legend>
            {data.levels.map((level) => (
              <label
                key={level.id}
                className="flex items-center gap-2 rounded-lg border p-2 text-sm has-[:checked]:border-primary has-[:checked]:bg-primary/5"
              >
                <input
                  type="radio"
                  name="level"
                  value={level.id}
                  checked={values.level_id === level.id}
                  onChange={() => setValues((v) => ({ ...v, level_id: level.id }))}
                />
                <span className="flex-1">{level.name}</span>
                {level.recruit_goal ? (
                  <span className="text-xs text-muted-foreground">
                    {level.recruit_goal === 1 ? "1 persona" : `${level.recruit_goal} personas`}
                  </span>
                ) : null}
              </label>
            ))}
          </fieldset>
          {/* Honeypot: hidden from people, filled by bots. */}
          <div aria-hidden className="absolute -left-[9999px] h-0 overflow-hidden">
            <label htmlFor="pub-website">Sitio web</label>
            <input
              id="pub-website"
              tabIndex={-1}
              autoComplete="off"
              value={values.website}
              onChange={set("website")}
            />
          </div>
          <div className="space-y-2 rounded-lg bg-muted/50 p-3">
            <div className="flex items-start gap-2">
              <Checkbox
                id="pub-accepts"
                checked={accepts}
                onCheckedChange={(c) => setAccepts(c === true)}
              />
              <Label htmlFor="pub-accepts" className="leading-snug font-normal">
                Leí y acepto el {data.notice.title} (versión {data.notice.version}) y doy mi
                consentimiento expreso para el tratamiento de mis datos.
              </Label>
            </div>
            <Button
              type="button"
              variant="link"
              className="h-auto p-0 text-xs"
              onClick={() => setShowNotice((s) => !s)}
              aria-expanded={showNotice}
            >
              {showNotice ? "Ocultar el aviso" : "Leer el aviso completo"}
            </Button>
            {showNotice ? (
              <div className="max-h-64 overflow-y-auto whitespace-pre-line rounded border bg-background p-3 text-xs">
                {data.notice.body}
              </div>
            ) : null}
          </div>
          <Button type="submit" size="lg" disabled={!ready || !proof || pending}>
            {pending ? "Enviando…" : !proof ? "Preparando verificación…" : "Inscribirme"}
          </Button>
          <p className="text-center text-xs text-muted-foreground">
            Tu inscripción la revisa una persona del Movimiento antes de activarse.
          </p>
        </form>
      </CardContent>
    </Card>
  );
}

function Field({
  id,
  label,
  error,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error ? (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
