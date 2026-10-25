import { AlertCircle } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { isProblem, problemMessage } from "@/lib/api";

export function ProblemAlert({ error, title }: { error: unknown; title?: string }) {
  if (!error) return null;
  const violations = isProblem(error) ? error.violations : undefined;
  return (
    <Alert variant="destructive">
      <AlertCircle aria-hidden />
      <AlertTitle>{title ?? (isProblem(error) ? error.title : "Error")}</AlertTitle>
      <AlertDescription>
        <p>{problemMessage(error)}</p>
        {violations?.length ? (
          <ul className="mt-1 list-disc pl-4">
            {violations.map((v) => (
              <li key={`${v.rule}-${v.formula_id ?? "n"}`}>{v.message}</li>
            ))}
          </ul>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}
