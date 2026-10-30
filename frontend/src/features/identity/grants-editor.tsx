import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import {
  getUserQueryKey,
  listRolesOptions,
  listUserGrantsOptions,
  listUserGrantsQueryKey,
  setUserGrantsMutation,
} from "@/client/@tanstack/react-query.gen";
import type { GrantIn, GrantOut } from "@/client/types.gen";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { ProblemAlert } from "@/components/problem-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { BranchesEditor } from "@/features/peace-movement/branches-editor";
import { type ScopeRow, ScopeRowsEditor } from "./scopes-editor";

const ORIGIN: Record<GrantOut["origin"], string> = {
  manual: "Manual",
  appointment: "Por nombramiento",
};

function toRows(grant: GrantOut): ScopeRow[] {
  return grant.scopes.map((s) => ({ level: s.level, node_id: s.node_id }));
}

function toIn(grant: GrantOut, rows?: ScopeRow[]): GrantIn {
  return {
    id: grant.id,
    role_id: grant.role.id,
    scopes: (rows ?? toRows(grant)).map(({ label: _l, ...s }) => s),
  };
}

/** Grants of a user (D-101): each one is a role with its own scope; the role's permissions
 * apply only inside that scope. Grants from an appointment follow it and are read-only here. */
export function GrantsEditor({
  userId,
  editable,
  showBranches,
}: {
  userId: string;
  editable: boolean;
  showBranches: boolean;
}) {
  const queryClient = useQueryClient();
  const key = listUserGrantsQueryKey({ path: { user_id: userId } });
  const grants = useQuery(listUserGrantsOptions({ path: { user_id: userId } }));
  const save = useMutation({
    ...setUserGrantsMutation(),
    onSuccess: (data) => {
      queryClient.setQueryData(key, data);
      queryClient.invalidateQueries({ queryKey: getUserQueryKey({ path: { user_id: userId } }) });
      queryClient.invalidateQueries({ queryKey: ["listUsers"] });
      toast.success("Concesiones actualizadas.");
    },
  });
  const all = grants.data ?? [];
  const manual = all.filter((g) => g.origin === "manual");
  const replace = (body: GrantIn[], onDone?: () => void) =>
    save.mutate({ path: { user_id: userId }, body: { grants: body } }, { onSuccess: onDone });

  return (
    <div className="space-y-4">
      <ProblemAlert error={save.error ?? grants.error} />
      {all.length ? (
        <ul className="space-y-3">
          {all.map((grant) => (
            <GrantItem
              key={grant.id}
              grant={grant}
              editable={editable && grant.origin === "manual"}
              showBranches={showBranches}
              branchesEditable={editable}
              pending={save.isPending}
              onRemove={() => replace(manual.filter((g) => g.id !== grant.id).map((g) => toIn(g)))}
              onSaveScopes={(rows, done) =>
                replace(
                  manual.map((g) => (g.id === grant.id ? toIn(g, rows) : toIn(g))),
                  done,
                )
              }
            />
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">
          Sin concesiones: el usuario no puede hacer nada en el sistema.
        </p>
      )}
      {editable ? (
        <NewGrant
          userId={userId}
          pending={save.isPending}
          onAdd={(roleId, rows, done) =>
            replace(
              [
                ...manual.map((g) => toIn(g)),
                { role_id: roleId, scopes: rows.map(({ label: _l, ...s }) => s) },
              ],
              done,
            )
          }
        />
      ) : null}
    </div>
  );
}

function GrantItem({
  grant,
  editable,
  showBranches,
  branchesEditable,
  pending,
  onRemove,
  onSaveScopes,
}: {
  grant: GrantOut;
  editable: boolean;
  showBranches: boolean;
  branchesEditable: boolean;
  pending: boolean;
  onRemove: () => void;
  onSaveScopes: (rows: ScopeRow[], done: () => void) => void;
}) {
  const [editing, setEditing] = useState<ScopeRow[] | null>(null);
  return (
    <li className="space-y-3 rounded-lg border p-3" aria-label={`Concesión ${grant.role.name}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{grant.role.name}</span>
        <Badge variant="secondary">{ORIGIN[grant.origin]}</Badge>
        {editable ? (
          <div className="ml-auto flex gap-1">
            {editing || grant.role.grants_all ? null : (
              <Button variant="ghost" size="sm" onClick={() => setEditing(toRows(grant))}>
                <Pencil aria-hidden /> Editar alcance
              </Button>
            )}
            <ConfirmDialog
              trigger={
                <Button variant="ghost" size="icon-sm" aria-label={`Quitar ${grant.role.name}`}>
                  <Trash2 aria-hidden />
                </Button>
              }
              title={`¿Quitar la concesión «${grant.role.name}»?`}
              description="El usuario pierde los permisos de este rol en su alcance."
              confirmLabel="Quitar"
              destructive
              onConfirm={onRemove}
            />
          </div>
        ) : null}
      </div>
      {grant.role.grants_all ? (
        <p className="text-sm text-muted-foreground">
          Todo el sistema: el superadministrador no tiene restricción geográfica.
        </p>
      ) : editing ? (
        <div className="space-y-2">
          <ScopeRowsEditor
            rows={editing}
            onChange={setEditing}
            editable
            idPrefix={`grant-${grant.id}`}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setEditing(null)}>
              Cancelar
            </Button>
            <Button
              size="sm"
              disabled={pending}
              onClick={() => onSaveScopes(editing, () => setEditing(null))}
            >
              Guardar alcance
            </Button>
          </div>
        </div>
      ) : (
        <ScopeRowsEditor
          rows={toRows(grant)}
          onChange={() => {}}
          editable={false}
          idPrefix={`grant-${grant.id}`}
        />
      )}
      {showBranches ? (
        <details className="text-sm">
          <summary className="cursor-pointer text-muted-foreground">
            Ramas del Movimiento de Paz de esta concesión
          </summary>
          <div className="mt-2">
            <BranchesEditor grantId={grant.id} editable={branchesEditable} />
          </div>
        </details>
      ) : null}
    </li>
  );
}

function NewGrant({
  userId,
  pending,
  onAdd,
}: {
  userId: string;
  pending: boolean;
  onAdd: (roleId: string, rows: ScopeRow[], done: () => void) => void;
}) {
  const roles = useQuery(listRolesOptions());
  const [roleId, setRoleId] = useState("");
  const [rows, setRows] = useState<ScopeRow[]>([]);
  const select = `new-grant-role-${userId}`;
  return (
    <div className="space-y-3 rounded-lg border border-dashed p-3">
      <div className="grid gap-1.5">
        <Label htmlFor={select}>Nueva concesión: rol</Label>
        <select
          id={select}
          value={roleId}
          onChange={(e) => setRoleId(e.target.value)}
          className="h-8 rounded-lg border border-input bg-transparent px-2 text-sm"
        >
          <option value="">Elige un rol…</option>
          {(roles.data ?? []).map((role) => (
            <option key={role.id} value={role.id}>
              {role.name}
            </option>
          ))}
        </select>
      </div>
      <ScopeRowsEditor rows={rows} onChange={setRows} editable idPrefix={`new-grant-${userId}`} />
      <div className="flex justify-end">
        <Button
          size="sm"
          disabled={!roleId || pending}
          onClick={() =>
            onAdd(roleId, rows, () => {
              setRoleId("");
              setRows([]);
            })
          }
        >
          <Plus aria-hidden /> Agregar concesión
        </Button>
      </div>
    </div>
  );
}
