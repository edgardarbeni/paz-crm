import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import type { PersonCreate, PersonOut, PersonUpdate } from "@/client/types.gen";
import { AsyncCombobox, type ComboItem } from "@/components/async-combobox";
import { FieldShell, submitOnModEnter, useAppForm } from "@/components/form/form";
import { ProblemAlert } from "@/components/problem-alert";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { curpCoherence, normalizeCurp, parseCurp } from "@/features/people/curp";
import { CURP_ENTITY_NAMES } from "@/features/people/entities";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";
import { blanksToNull } from "@/lib/forms";
import { options, SEX_LABELS } from "@/lib/labels";
import { GEO_SEARCH_HINTS, type GeoSearchLevel, searchGeoItems } from "@/lib/search";

const CONTACT_TYPES = { mobile: "Celular", landline: "Teléfono fijo", email: "Correo" };
type GeoKey = "state" | "municipality" | "section" | "locality" | "neighborhood";
const GEO_FIELDS: [GeoKey, string][] = [
  ["state", "Estado"],
  ["municipality", "Municipio"],
  ["section", "Sección electoral"],
  ["locality", "Localidad"],
  ["neighborhood", "Colonia"],
];

interface ContactRow {
  contact_type: "mobile" | "landline" | "email";
  value: string;
  is_primary: boolean;
}

function nodeItem(id: string | null | undefined, label: string): ComboItem | null {
  return id ? { id, label } : null;
}

/**
 * Person capture/edit (D-30, D-31). The CURP is validated as you type; birth date, sex and
 * entity are derived from it when empty, and mismatches are shown before saving. Without
 * `read_sensitive`, stored contacts and street are masked, so they are replaced only when the
 * user chooses to edit them.
 */
export function PersonForm({
  person,
  error,
  onSubmit,
}: {
  person?: PersonOut;
  error: unknown;
  onSubmit: (body: PersonCreate | PersonUpdate) => Promise<unknown>;
}) {
  const can = useCan();
  const sensitive = can(Perm.PERSON_READ_SENSITIVE);
  const address = person?.addresses[0];
  const [editContacts, setEditContacts] = useState(!person || sensitive);
  const [editAddress, setEditAddress] = useState(!person || sensitive);
  const [geo, setGeo] = useState<Record<GeoKey, ComboItem | null>>({
    state: nodeItem(address?.state_id, "Estado registrado"),
    municipality: nodeItem(address?.municipality_id, "Municipio registrado"),
    section: nodeItem(address?.section_id, "Sección registrada"),
    locality: nodeItem(address?.locality_id, "Localidad registrada"),
    neighborhood: nodeItem(address?.neighborhood_id, "Colonia registrada"),
  });

  const form = useAppForm({
    defaultValues: {
      given_names: person?.given_names ?? "",
      paternal_surname: person?.paternal_surname ?? "",
      maternal_surname: person?.maternal_surname ?? "",
      sex: person?.sex ?? "",
      birth_date: person?.birth_date ?? "",
      birth_entity: person?.birth_entity ?? "",
      curp: person && sensitive ? (person.curp ?? "") : "",
      accept_curp_incoherence: false,
      contacts: (sensitive ? (person?.contacts ?? []) : []).map((c) => ({
        contact_type: c.contact_type as ContactRow["contact_type"],
        value: c.value,
        is_primary: c.is_primary,
      })) as ContactRow[],
      street: (sensitive && address?.street) || "",
      exterior_number: (sensitive && address?.exterior_number) || "",
      interior_number: (sensitive && address?.interior_number) || "",
      references: (sensitive && address?.references) || "",
      postal_code: address?.postal_code ?? "",
    },
    onSubmit: async ({ value }) => {
      const clean = blanksToNull(value);
      const hasAddress =
        Object.values(geo).some(Boolean) ||
        [clean.street, clean.exterior_number, clean.postal_code].some(Boolean);
      const body: PersonCreate | PersonUpdate = {
        given_names: clean.given_names,
        paternal_surname: clean.paternal_surname,
        maternal_surname: clean.maternal_surname,
        sex: clean.sex as PersonCreate["sex"],
        birth_date: clean.birth_date,
        birth_entity: clean.birth_entity,
        // Edit without sensitive access: an empty CURP field means "unchanged".
        ...(clean.curp ? { curp: normalizeCurp(clean.curp) } : {}),
        accept_curp_incoherence: value.accept_curp_incoherence,
        ...(editContacts ? { contacts: clean.contacts.filter((c) => c.value) } : {}),
        ...(editAddress && hasAddress
          ? {
              address: {
                street: clean.street,
                exterior_number: clean.exterior_number,
                interior_number: clean.interior_number,
                references: clean.references,
                postal_code: clean.postal_code,
                state_id: geo.state?.id ?? null,
                municipality_id: geo.municipality?.id ?? null,
                section_id: geo.section?.id ?? null,
                locality_id: geo.locality?.id ?? null,
                neighborhood_id: geo.neighborhood?.id ?? null,
              },
            }
          : {}),
      };
      await onSubmit(body).catch(() => {});
    },
  });

  return (
    <form
      className="grid gap-6"
      noValidate
      onKeyDown={submitOnModEnter}
      onSubmit={(event) => {
        event.preventDefault();
        form.handleSubmit();
      }}
    >
      <ProblemAlert error={error} title="No se pudo guardar" />
      <Card>
        <CardHeader>
          <CardTitle>
            <h2>Datos generales</h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-3 md:grid-cols-3">
            <form.AppField
              name="given_names"
              validators={{ onBlur: ({ value }) => (value.trim() ? undefined : "Obligatorio.") }}
            >
              {(field) => (
                <field.TextField label="Nombre(s)" autoFocus required autoComplete="off" />
              )}
            </form.AppField>
            <form.AppField
              name="paternal_surname"
              validators={{ onBlur: ({ value }) => (value.trim() ? undefined : "Obligatorio.") }}
            >
              {(field) => <field.TextField label="Primer apellido" required autoComplete="off" />}
            </form.AppField>
            <form.AppField name="maternal_surname">
              {(field) => <field.TextField label="Segundo apellido" autoComplete="off" />}
            </form.AppField>
          </div>
          <form.AppField
            name="curp"
            validators={{
              onChange: ({ value }) => {
                const curp = normalizeCurp(value);
                if (curp.length < 18) return undefined;
                const result = parseCurp(curp);
                return result.ok ? undefined : result.error;
              },
              onBlur: ({ value }) => {
                const curp = normalizeCurp(value);
                if (!curp) return undefined;
                const result = parseCurp(curp);
                return result.ok ? undefined : result.error;
              },
            }}
            listeners={{
              onChange: ({ value }) => {
                const result = parseCurp(value);
                if (!result.ok) return;
                // Fill only what is still empty; mismatches are reported below.
                if (!form.getFieldValue("birth_date"))
                  form.setFieldValue("birth_date", result.data.birthDate);
                if (!form.getFieldValue("sex")) form.setFieldValue("sex", result.data.sex);
                if (!form.getFieldValue("birth_entity"))
                  form.setFieldValue("birth_entity", result.data.birthEntity);
              },
            }}
          >
            {(field) => (
              <field.TextField
                label="CURP"
                maxLength={18}
                normalize={normalizeCurp}
                autoComplete="off"
                className="md:max-w-sm"
                description={
                  person?.curp && !sensitive
                    ? `Registrada: ${person.curp}. Déjala vacía para conservarla.`
                    : "Se valida estructura y dígito verificador; llena fecha, sexo y entidad."
                }
              />
            )}
          </form.AppField>
          <div className="grid gap-3 md:grid-cols-3">
            <form.AppField name="birth_date">
              {(field) => <field.TextField label="Fecha de nacimiento" type="date" />}
            </form.AppField>
            <form.AppField name="sex">
              {(field) => <field.SelectField label="Sexo" options={options(SEX_LABELS)} />}
            </form.AppField>
            <form.AppField name="birth_entity">
              {(field) => (
                <field.SelectField
                  label="Entidad de nacimiento"
                  options={options(CURP_ENTITY_NAMES)}
                />
              )}
            </form.AppField>
          </div>
          <form.Subscribe selector={(s) => s.values}>
            {(values) => {
              const result = parseCurp(values.curp);
              const problems = result.ok
                ? curpCoherence(result.data, {
                    birthDate: values.birth_date,
                    sex: values.sex,
                    birthEntity: values.birth_entity,
                  })
                : [];
              return problems.length ? (
                <Alert variant="destructive">
                  <AlertTitle>La CURP no coincide con los datos</AlertTitle>
                  <AlertDescription>
                    <ul className="list-disc pl-4">
                      {problems.map((p) => (
                        <li key={p}>{p}</li>
                      ))}
                    </ul>
                    {sensitive ? (
                      <form.AppField name="accept_curp_incoherence">
                        {(field) => (
                          <field.CheckboxField label="Registrar de todos modos (queda marcado)" />
                        )}
                      </form.AppField>
                    ) : (
                      <p>Corrige los datos o pide a un coordinador que autorice el registro.</p>
                    )}
                  </AlertDescription>
                </Alert>
              ) : null;
            }}
          </form.Subscribe>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>
            <h2>Contactos</h2>
          </CardTitle>
          {!editContacts ? (
            <Button type="button" variant="outline" size="sm" onClick={() => setEditContacts(true)}>
              Reemplazar contactos
            </Button>
          ) : null}
        </CardHeader>
        <CardContent>
          {!editContacts ? (
            <ul className="text-sm">
              {person?.contacts.length ? (
                person.contacts.map((c) => (
                  <li key={c.id}>
                    {CONTACT_TYPES[c.contact_type as ContactRow["contact_type"]]}: {c.value}
                    {c.is_primary ? " (principal)" : ""}
                  </li>
                ))
              ) : (
                <li className="text-muted-foreground">Sin contactos.</li>
              )}
            </ul>
          ) : (
            <form.AppField name="contacts" mode="array">
              {(field) => (
                <div className="grid gap-2">
                  {field.state.value.map((_, index) => (
                    <div
                      // biome-ignore lint/suspicious/noArrayIndexKey: rows are positional (TanStack Form array)
                      key={index}
                      className="grid grid-cols-[9rem_1fr_auto_auto] items-end gap-2"
                    >
                      <form.AppField name={`contacts[${index}].contact_type`}>
                        {(sub) => (
                          <sub.SelectField
                            label="Tipo"
                            options={options(CONTACT_TYPES)}
                            placeholder="Tipo…"
                          />
                        )}
                      </form.AppField>
                      <form.AppField name={`contacts[${index}].value`}>
                        {(sub) => <sub.TextField label="Valor" autoComplete="off" />}
                      </form.AppField>
                      <form.AppField name={`contacts[${index}].is_primary`}>
                        {(sub) => <sub.CheckboxField label="Principal" />}
                      </form.AppField>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        aria-label="Quitar contacto"
                        onClick={() => field.removeValue(index)}
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
                    onClick={() =>
                      field.pushValue({
                        contact_type: "mobile",
                        value: "",
                        is_primary: field.state.value.length === 0,
                      })
                    }
                  >
                    <Plus aria-hidden /> Agregar contacto
                  </Button>
                </div>
              )}
            </form.AppField>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>
            <h2>Domicilio</h2>
          </CardTitle>
          {!editAddress ? (
            <Button type="button" variant="outline" size="sm" onClick={() => setEditAddress(true)}>
              Reemplazar domicilio
            </Button>
          ) : null}
        </CardHeader>
        <CardContent className="grid gap-4">
          {!editAddress ? (
            <p className="text-sm text-muted-foreground">
              {address
                ? "Domicilio registrado (los datos de calle están protegidos)."
                : "Sin domicilio."}
            </p>
          ) : (
            <>
              <div className="grid gap-3 md:grid-cols-[2fr_1fr_1fr]">
                <form.AppField name="street">
                  {(field) => <field.TextField label="Calle" autoComplete="off" />}
                </form.AppField>
                <form.AppField name="exterior_number">
                  {(field) => <field.TextField label="Núm. exterior" />}
                </form.AppField>
                <form.AppField name="interior_number">
                  {(field) => <field.TextField label="Núm. interior" />}
                </form.AppField>
              </div>
              <div className="grid gap-3 md:grid-cols-[1fr_3fr]">
                <form.AppField name="postal_code">
                  {(field) => (
                    <field.TextField label="Código postal" inputMode="numeric" maxLength={5} />
                  )}
                </form.AppField>
                <form.AppField name="references">
                  {(field) => <field.TextField label="Referencias" />}
                </form.AppField>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                {GEO_FIELDS.map(([key, label]) => (
                  <FieldShell key={key} id={`address-${key}`} label={label}>
                    <AsyncCombobox
                      id={`address-${key}`}
                      label={label}
                      value={geo[key]}
                      onChange={(item) => setGeo((g) => ({ ...g, [key]: item }))}
                      // Once the state is chosen, the other levels only search inside it.
                      queryKey={["geo-search", key, key === "state" ? null : geo.state?.id]}
                      search={(term) =>
                        searchGeoItems(term, [key as GeoSearchLevel], {
                          stateId: key === "state" ? null : geo.state?.id,
                        })
                      }
                      minChars={key === "state" || key === "section" ? 1 : 2}
                      placeholder={GEO_SEARCH_HINTS[key]}
                    />
                  </FieldShell>
                ))}
              </div>
            </>
          )}
        </CardContent>
      </Card>
      <form.AppForm>
        <form.SubmitButton className="justify-self-start">Guardar persona</form.SubmitButton>
      </form.AppForm>
    </form>
  );
}
