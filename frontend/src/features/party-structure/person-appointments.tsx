import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { listPersonAppointmentsOptions } from "@/client/@tanstack/react-query.gen";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";
import { formatDate } from "@/lib/labels";
import { APPOINTMENT_KIND } from "./labels";

/** The person's current party positions (in bodies the user may see, D-108). */
export function PersonAppointments({ personId }: { personId: string }) {
  const can = useCan();
  const appointments = useQuery({
    ...listPersonAppointmentsOptions({ path: { person_id: personId } }),
    enabled: can(Perm.STRUCTURE_APPOINTMENT_READ),
  });
  if (!can(Perm.STRUCTURE_APPOINTMENT_READ) || !appointments.data?.length) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Cargos en el partido</h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2 text-sm" aria-label="Cargos en el partido">
          {appointments.data.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center gap-2">
              <Link
                to="/structure/bodies/$bodyId"
                params={{ bodyId: a.body_id }}
                className="font-medium underline-offset-4 hover:underline"
              >
                {a.position_type.name}
              </Link>
              <span className="text-muted-foreground">{a.territory}</span>
              <span className="text-xs text-muted-foreground">
                {APPOINTMENT_KIND[a.kind]} desde {formatDate(a.starts_on)}
              </span>
              {a.has_access ? <Badge variant="outline">Con acceso</Badge> : null}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
