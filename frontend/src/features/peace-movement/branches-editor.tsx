import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Plus, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import {
  listUserBranchesOptions,
  listUserBranchesQueryKey,
  setUserBranchesMutation,
} from "@/client/@tanstack/react-query.gen";
import type { ComboItem } from "@/components/async-combobox";
import { ProblemAlert } from "@/components/problem-alert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { MemberPicker } from "./shared";

/** Branch scope of a user (D-83): the whole network under each assigned member, across states.
 * Only a branch inside one the actor already has can be granted (anti-escalation). */
export function BranchesEditor({ userId, editable }: { userId: string; editable: boolean }) {
  const queryClient = useQueryClient();
  const key = listUserBranchesQueryKey({ path: { user_id: userId } });
  const branches = useQuery(listUserBranchesOptions({ path: { user_id: userId } }));
  const [picked, setPicked] = useState<ComboItem | null>(null);
  const save = useMutation({
    ...setUserBranchesMutation(),
    onSuccess: (data) => {
      queryClient.setQueryData(key, data);
      setPicked(null);
      toast.success("Ramas actualizadas.");
    },
  });
  const current = branches.data ?? [];
  const replace = (memberIds: string[]) =>
    save.mutate({ path: { user_id: userId }, body: { member_ids: memberIds } });
  return (
    <div className="space-y-3">
      <ProblemAlert error={branches.error ?? save.error} />
      {current.length ? (
        <ul className="space-y-1">
          {current.map((branch) => (
            <li key={branch.member_id} className="flex items-center justify-between gap-2 text-sm">
              <Link
                to="/peace-movement/members/$memberId"
                params={{ memberId: branch.member_id }}
                className="underline-offset-4 hover:underline"
              >
                {branch.person.full_name}
              </Link>
              {editable ? (
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={`Quitar la rama de ${branch.person.full_name}`}
                  disabled={save.isPending}
                  onClick={() =>
                    replace(current.map((b) => b.member_id).filter((id) => id !== branch.member_id))
                  }
                >
                  <X aria-hidden />
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">
          Sin ramas: solo ve pacificadores por su alcance geográfico.
        </p>
      )}
      {editable ? (
        <form
          className="flex items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (picked) replace([...current.map((b) => b.member_id), picked.id]);
          }}
        >
          <div className="grid flex-1 gap-1.5">
            <Label htmlFor={`branch-${userId}`}>Agregar la red de un pacificador</Label>
            <MemberPicker
              id={`branch-${userId}`}
              label="Pacificador"
              value={picked}
              onChange={setPicked}
              activeOnly={false}
            />
          </div>
          <Button type="submit" variant="outline" disabled={!picked || save.isPending}>
            <Plus aria-hidden /> Agregar
          </Button>
        </form>
      ) : null}
    </div>
  );
}
