import { Copy, Download } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";

export function RecoveryCodes({ codes }: { codes: string[] }) {
  const text = codes.join("\n");
  return (
    <div className="space-y-3">
      <p className="text-sm">
        Guarda estos códigos en un lugar seguro. Cada uno sirve una sola vez si pierdes tu
        dispositivo. <strong>No se volverán a mostrar.</strong>
      </p>
      <ul
        aria-label="Códigos de recuperación"
        className="grid grid-cols-2 gap-1 rounded-lg border bg-muted/40 p-3 font-mono text-sm"
      >
        {codes.map((code) => (
          <li key={code}>{code}</li>
        ))}
      </ul>
      <div className="flex gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() =>
            navigator.clipboard.writeText(text).then(() => toast.success("Códigos copiados."))
          }
        >
          <Copy aria-hidden /> Copiar
        </Button>
        <Button type="button" variant="outline" size="sm" asChild>
          <a
            href={`data:text/plain;charset=utf-8,${encodeURIComponent(text)}`}
            download="pazos-codigos-recuperacion.txt"
          >
            <Download aria-hidden /> Descargar
          </a>
        </Button>
      </div>
    </div>
  );
}
