import type { StandardSchemaV1 } from "@tanstack/react-form";
import { z } from "zod";

/** Spanish validation messages for every schema (generated ones included). */
export function configureZod() {
  z.config(z.locales.es());
}

/** Form state uses "" for empty inputs; the API expects null/absent. */
export function blanksToNull<T>(value: T): T {
  if (typeof value === "string") {
    const trimmed = value.trim();
    return (trimmed === "" ? null : trimmed) as T;
  }
  if (Array.isArray(value)) return value.map(blanksToNull) as T;
  if (value && typeof value === "object" && !(value instanceof Date)) {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, blanksToNull(item)]),
    ) as T;
  }
  return value;
}

/** Wraps a generated (API) schema so blank inputs validate as null (e.g. optional CURP).
 * Typed by the form's values, which differ from the API shape only in blanks. */
// biome-ignore lint/suspicious/noExplicitAny: accepts any form-values shape (blanks vs nulls)
export function formSchema(schema: z.ZodType): StandardSchemaV1<any, unknown> {
  return z.preprocess(blanksToNull, schema);
}
