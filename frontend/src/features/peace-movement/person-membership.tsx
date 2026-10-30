import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { HandHeart } from "lucide-react";
import { searchMembersOptions } from "@/client/@tanstack/react-query.gen";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";
import { formatDate } from "@/lib/labels";
import { MemberStatusBadge, useLevels } from "./shared";

const CURRENT = new Set(["active", "pending_validation"]);

/** The person's participation in the Peace Movement, on their profile (people only references
 * the module from the panel; the API keeps them independent). */
export function PersonMembership({ personId }: { personId: string }) {
  const can = useCan();
  const { byId } = useLevels();
  const memberships = useQuery({
    ...searchMembersOptions({ query: { person_id: personId, limit: 10 } }),
    enabled: can(Perm.PEACE_MEMBER_READ),
  });
  if (!can(Perm.PEACE_MEMBER_READ) || !memberships.data) return null;
  const items = memberships.data.items;
  const current = items.find((m) => CURRENT.has(m.status));
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Movimiento de Paz</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {items.length ? (
          <ul className="space-y-2">
            {items.map((member) => (
              <li key={member.id} className="flex flex-wrap items-center gap-2">
                <Link
                  to="/peace-movement/members/$memberId"
                  params={{ memberId: member.id }}
                  className="font-medium underline-offset-4 hover:underline"
                >
                  {byId.get(member.level_id)?.name ?? "Pacificador"}
                </Link>
                <MemberStatusBadge status={member.status} />
                <span className="text-xs text-muted-foreground">
                  desde {formatDate(member.enrolled_on)}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground">No participa en el Movimiento de Paz.</p>
        )}
        {!current && can(Perm.PEACE_MEMBER_WRITE) ? (
          <Button asChild variant="outline" size="sm">
            <Link to="/peace-movement/members/new" search={{ person: personId }}>
              <HandHeart aria-hidden /> Inscribir en el Movimiento de Paz
            </Link>
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}
