/** Labels and helpers of the Peace Movement (docs/modules/peace-movement.md). */

export const MEMBER_STATUS: Record<string, string> = {
  pending_validation: "Pendiente de validar",
  active: "Activo",
  rejected: "Rechazado",
  left: "Dejó el movimiento",
  withdrawn: "Baja (ARCO)",
};

export const MEMBER_STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "destructive" | "outline"
> = {
  pending_validation: "secondary",
  active: "default",
  rejected: "destructive",
  left: "outline",
  withdrawn: "outline",
};

export const ORIGIN: Record<string, string> = {
  recruiter: "Reclutado por un pacificador",
  structure: "Estructura del partido",
  event: "Evento",
  campaign: "Campaña",
};

export const CHANNEL: Record<string, string> = {
  panel: "Panel",
  referral_link: "Enlace o QR",
  import: "Importación",
  field_app: "App de campo",
};

export const HOUSE_STATUS: Record<string, string> = {
  open: "Abierta",
  consolidated: "Consolidada",
  closed: "Cerrada",
};

export const HOUSE_STATUS_VARIANT: Record<string, "default" | "secondary" | "outline"> = {
  open: "secondary",
  consolidated: "default",
  closed: "outline",
};

export const HOUSE_MEMBER_SOURCE: Record<string, string> = {
  enrollment: "Al inscribirse",
  assignment: "Asignado",
  role: "Anfitrión o contacto",
};

export const TRAFFIC_LIGHT: Record<string, { label: string; className: string }> = {
  red: { label: "Rezagado", className: "bg-red-100 text-red-800 ring-red-200" },
  yellow: { label: "En camino", className: "bg-amber-100 text-amber-900 ring-amber-200" },
  green: { label: "Meta cumplida", className: "bg-emerald-100 text-emerald-800 ring-emerald-200" },
};

export const IMPORT_STATUS: Record<string, string> = {
  queued: "En cola",
  running: "Procesando",
  done: "Terminada",
  failed: "Falló",
};

export const WEEKDAYS: Record<string, string> = {
  mon: "Lunes",
  tue: "Martes",
  wed: "Miércoles",
  thu: "Jueves",
  fri: "Viernes",
  sat: "Sábado",
  sun: "Domingo",
};

/** Same look as the panel's other native selects (D-75: native selects for short catalogs). */
export const SELECT_CLASS =
  "h-8 rounded-lg border border-input bg-transparent px-2 text-sm focus-visible:border-ring focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50";

const number = new Intl.NumberFormat("es-MX");

export function formatCount(value: number | null | undefined): string {
  return value == null ? "—" : number.format(value);
}
