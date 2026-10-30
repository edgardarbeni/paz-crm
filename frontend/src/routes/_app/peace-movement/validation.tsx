import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Check } from "lucide-react";
import { toast } from "sonner";
import {
  rejectMemberMutation,
  searchMembersOptions,
  validateMemberMutation,
} from "@/client/@tanstack/react-query.gen";
import type { MemberSummary } from "@/client/types.gen";
import { useCursorPager } from "@/components/data/use-cursor-pager";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ReasonDialog, useLevels } from "@/features/peace-movement/shared";
import { formatDate } from "@/lib/labels";

export const Route = createFileRoute("/_app/peace-movement/validation")({
  component: ValidationPage,
});

/** Queue of enrollments that arrived through the public link or the field app (D-92): they do
 * not count for goals until someone with `member.validate` checks them. */
function ValidationPage() {
  const queryClient = useQueryClient();
  const { cursor, pager } = useCursorPager("pending");
  const pending = useQuery(
    searchMembersOptions({
      query: { status: "pending_validation", sort: "created_at", cursor, limit: 25 },
    }),
  );
  const refresh = () => queryClient.invalidateQueries({ queryKey: [{ _id: "searchMembers" }] });
  const page = pager(pending.data);

  return (
    <section className="max-w-4xl">
      <PageHeader
        title="Validación de inscripciones"
        description="Inscripciones por enlace, QR o app de campo. No cuentan para las metas hasta validarse. Abre cada una para comparar los datos si la persona ya estaba registrada."
      />
      <ProblemAlert error={pending.error} />
      {pending.data && pending.data.items.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            No hay inscripciones pendientes.
          </CardContent>
        </Card>
      ) : null}
      <ul className="space-y-2">
        {pending.data?.items.map((member) => (
          <PendingRow key={member.id} member={member} onDone={refresh} />
        ))}
      </ul>
      {page.hasMore || page.canPrev ? (
        <div className="mt-4 flex gap-2">
          <Button variant="outline" disabled={!page.canPrev} onClick={page.prev}>
            Anterior
          </Button>
          <Button variant="outline" disabled={!page.hasMore} onClick={page.next}>
            Siguiente
          </Button>
        </div>
      ) : null}
    </section>
  );
}

function PendingRow({ member, onDone }: { member: MemberSummary; onDone: () => void }) {
  const { byId } = useLevels();
  const validate = useMutation({
    ...validateMemberMutation(),
    onSuccess: () => {
      toast.success(`${member.person.full_name} validado.`);
      onDone();
    },
  });
  const reject = useMutation({ ...rejectMemberMutation(), onSuccess: onDone });
  return (
    <li>
      <Card>
        <CardContent className="flex flex-wrap items-center gap-3">
          <div className="min-w-0 flex-1">
            <Link
              to="/peace-movement/members/$memberId"
              params={{ memberId: member.id }}
              className="font-medium underline-offset-4 hover:underline"
            >
              {member.person.full_name}
            </Link>
            <p className="text-xs text-muted-foreground">
              {byId.get(member.level_id)?.name} · inscripción del {formatDate(member.enrolled_on)}
              {member.person.curp ? ` · CURP ${member.person.curp}` : ""}
            </p>
            <ProblemAlert error={validate.error} />
          </div>
          <Button
            size="sm"
            disabled={validate.isPending}
            onClick={() => validate.mutate({ path: { member_id: member.id } })}
          >
            <Check aria-hidden /> Validar
          </Button>
          <ReasonDialog
            trigger={
              <Button size="sm" variant="outline">
                Rechazar
              </Button>
            }
            title={`Rechazar a ${member.person.full_name}`}
            confirmLabel="Rechazar"
            destructive
            error={reject.error}
            pending={reject.isPending}
            onConfirm={(reason) =>
              reject.mutateAsync({ path: { member_id: member.id }, body: { reason } })
            }
          />
        </CardContent>
      </Card>
    </li>
  );
}
