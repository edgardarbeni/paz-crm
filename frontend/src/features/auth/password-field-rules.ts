import { z } from "zod";

/** Mirrors the backend minimum (identity password policy); the API is authoritative. */
export const newPassword = z
  .object({
    password: z.string().min(12, "Usa al menos 12 caracteres."),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, {
    message: "Las contraseñas no coinciden.",
    path: ["confirm"],
  });
