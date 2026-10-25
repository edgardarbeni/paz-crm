import type { SessionOut } from "@/client/types.gen";
import { Badge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/labels";

export function SessionsTable({
  sessions,
  onRevoke,
}: {
  sessions: SessionOut[];
  onRevoke?: (session: SessionOut) => void;
}) {
  if (!sessions.length)
    return <p className="text-sm text-muted-foreground">Sin sesiones activas.</p>;
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <caption className="sr-only">Sesiones activas</caption>
        <thead className="bg-muted/50 text-left text-muted-foreground">
          <tr>
            <th scope="col" className="px-3 py-2">
              Dispositivo
            </th>
            <th scope="col" className="px-3 py-2">
              IP
            </th>
            <th scope="col" className="px-3 py-2">
              Inicio
            </th>
            <th scope="col" className="px-3 py-2">
              Última actividad
            </th>
            {onRevoke ? (
              <th scope="col" className="px-3 py-2">
                <span className="sr-only">Acciones</span>
              </th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {sessions.map((s) => (
            <tr key={s.id} className="border-t">
              <td className="max-w-xs truncate px-3 py-2" title={s.user_agent ?? undefined}>
                {s.device_label ?? s.user_agent ?? "—"}{" "}
                {s.current ? <Badge variant="secondary">Esta sesión</Badge> : null}
              </td>
              <td className="px-3 py-2">{s.ip_address ?? "—"}</td>
              <td className="px-3 py-2">{formatDateTime(s.created_at)}</td>
              <td className="px-3 py-2">{formatDateTime(s.last_seen_at)}</td>
              {onRevoke ? (
                <td className="px-3 py-2 text-right">
                  {!s.current ? (
                    <button
                      type="button"
                      className="text-sm text-destructive underline-offset-4 hover:underline"
                      onClick={() => onRevoke(s)}
                    >
                      Cerrar
                    </button>
                  ) : null}
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
