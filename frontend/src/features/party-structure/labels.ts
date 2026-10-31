export const LEVEL: Record<string, string> = {
  national: "Nacional",
  state: "Estatal",
  district: "Distrital",
  municipal: "Municipal o de alcaldía",
  coordination: "Coordinación territorial",
};

export const COORDINATION_KIND: Record<string, string> = {
  federal: "Federal (distritos federales)",
  local: "Local (distritos locales)",
  sectional: "Seccional (secciones)",
};

export const APPOINTMENT_KIND: Record<string, string> = {
  elected: "Electo",
  designated: "Designado",
  acting: "Encargado de despacho",
  delegate: "Delegación en funciones",
};

export const END_REASON: Record<string, string> = {
  term_end: "Fin del periodo",
  resignation: "Renuncia",
  removal: "Remoción",
  death: "Fallecimiento",
  other: "Otro",
};

export const ISSUE_KIND: Record<string, string> = {
  committee_without_territory: "Comité sin territorio",
  coordination_nodes_removed: "Coordinación con territorio perdido",
};

/** INE state codes are 1–32; names come from the active framework in each body's `territory`. */
export const STATE_CODES = Array.from({ length: 32 }, (_, i) => i + 1);
