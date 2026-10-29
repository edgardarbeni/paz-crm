/** Spanish labels for API enums (the API speaks English codes). */
export const GEO_LEVEL_LABELS: Record<string, string> = {
  national: "Nacional",
  electoral_region: "Circunscripción",
  state: "Estado",
  federal_district: "Distrito federal",
  local_district: "Distrito local",
  municipality: "Municipio",
  section: "Sección",
  locality: "Localidad",
  neighborhood: "Colonia",
};

export const GEO_LEVEL_PLURALS: Record<string, string> = {
  electoral_region: "Circunscripciones",
  state: "Estados",
  federal_district: "Distritos federales",
  local_district: "Distritos locales",
  municipality: "Municipios",
  section: "Secciones",
  locality: "Localidades",
  neighborhood: "Colonias",
};

export const SEX_LABELS: Record<string, string> = { H: "Hombre", M: "Mujer", X: "No binario" };

export const NOMINATION_STATUS: Record<string, string> = {
  draft: "Borrador",
  submitted: "Enviada",
  approved: "Aprobada",
  cancelled: "Cancelada",
};

export const FORMULA_STATUS: Record<string, string> = {
  aspirant: "Aspirante",
  registered: "Registrada",
  approved: "Aprobada",
  substituted: "Sustituida",
  cancelled: "Cancelada",
};

export const PROCESS_STATUS: Record<string, string> = {
  draft: "Borrador",
  active: "Activo",
  closed: "Cerrado",
};

export const ELECTION_LEVEL: Record<string, string> = { federal: "Federal", local: "Local" };
export const PRINCIPLE: Record<string, string> = {
  mr: "Mayoría relativa",
  rp: "Representación proporcional",
};
export const NOMINATION_KIND: Record<string, string> = {
  single: "Fórmula única",
  list: "Lista",
  slate: "Planilla",
  member: "Integrante de planilla",
};
export const RP_METHOD: Record<string, string> = {
  closed_list: "Lista cerrada",
  best_loser: "Mejor perdedor",
  mixed: "Mixto",
};
export const USER_STATUS: Record<string, string> = {
  active: "Activo",
  invited: "Invitado",
  disabled: "Deshabilitado",
  locked: "Bloqueado",
};
export const SEVERITY: Record<string, string> = { blocking: "Bloqueante", warning: "Advertencia" };
export const ELECTION_REGIME: Record<string, string> = {
  party_based: "Partidos políticos",
  normative_system: "Sistemas normativos internos",
};

export const RUN_STATUS: Record<string, string> = {
  running: "En curso",
  succeeded: "Exitosa",
  failed: "Fallida",
};

export function options(labels: Record<string, string>) {
  return Object.entries(labels).map(([value, label]) => ({ value, label }));
}

const dateTime = new Intl.DateTimeFormat("es-MX", { dateStyle: "medium", timeStyle: "short" });
const dateOnly = new Intl.DateTimeFormat("es-MX", { dateStyle: "medium", timeZone: "UTC" });

export function formatDateTime(value: string | null | undefined): string {
  return value ? dateTime.format(new Date(value)) : "—";
}

export function formatDate(value: string | null | undefined): string {
  return value ? dateOnly.format(new Date(`${value}T00:00:00Z`)) : "—";
}
