import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import {
  createCoalitionMutation,
  listCoalitionsOptions,
  listCoalitionsQueryKey,
  listPartiesOptions,
} from "@/client/@tanstack/react-query.gen";
import { FormDialog } from "@/components/form-dialog";
import { LabeledToggle } from "@/components/labeled-toggle";
import { ProblemAlert } from "@/components/problem-alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const KIND: Record<string, string> = {
  coalition: "Coalición",
  common_candidacy: "Candidatura común",
};

export function CoalitionsTab({ processId, editable }: { processId: string; editable: boolean }) {
  const coalitions = useQuery(listCoalitionsOptions({ path: { process_id: processId } }));
  const parties = useQuery(listPartiesOptions());
  const [creating, setCreating] = useState(false);
  const partyName = new Map((parties.data ?? []).map((p) => [p.id, p.acronym]));
  return (
    <div className="space-y-4">
      <ProblemAlert error={coalitions.error} />
      {coalitions.data?.length ? (
        <ul className="divide-y rounded-lg border">
          {coalitions.data.map((c) => (
            <li key={c.id} className="flex items-center justify-between px-3 py-2 text-sm">
              <span>
                <span className="font-medium">{c.name}</span>{" "}
                <span className="text-muted-foreground">· {KIND[c.coalition_kind]}</span>
              </span>
              <span>{c.party_ids.map((id) => partyName.get(id) ?? "?").join(" · ")}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">Sin coaliciones registradas.</p>
      )}
      {editable ? (
        <Button variant="outline" onClick={() => setCreating(true)}>
          <Plus aria-hidden /> Nueva coalición
        </Button>
      ) : null}
      {creating ? (
        <CoalitionDialog processId={processId} onClose={() => setCreating(false)} />
      ) : null}
    </div>
  );
}

function CoalitionDialog({ processId, onClose }: { processId: string; onClose: () => void }) {
  const queryClient = useQueryClient();
  const parties = useQuery(listPartiesOptions());
  const [name, setName] = useState("");
  const [kind, setKind] = useState<"coalition" | "common_candidacy">("coalition");
  const [selected, setSelected] = useState<string[]>([]);
  const create = useMutation({
    ...createCoalitionMutation(),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: listCoalitionsQueryKey({ path: { process_id: processId } }),
      });
      onClose();
    },
  });
  return (
    <FormDialog open onOpenChange={(open) => !open && onClose()} title="Nueva coalición">
      <form
        className="grid gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate({
            path: { process_id: processId },
            body: { name, coalition_kind: kind, party_ids: selected },
          });
        }}
      >
        <ProblemAlert error={create.error} />
        <div className="grid gap-1.5">
          <Label htmlFor="coalition-name">Nombre</Label>
          <Input
            id="coalition-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
            required
            minLength={2}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="coalition-kind">Tipo</Label>
          <select
            id="coalition-kind"
            value={kind}
            onChange={(e) => setKind(e.target.value as typeof kind)}
            className="h-8 rounded-lg border border-input bg-transparent px-2 text-sm"
          >
            {Object.entries(KIND).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <fieldset className="grid gap-2">
          <legend className="mb-1 text-sm font-medium">Partidos (mínimo 2)</legend>
          {(parties.data ?? []).map((party) => (
            <LabeledToggle
              key={party.id}
              checked={selected.includes(party.id)}
              onCheckedChange={(checked) =>
                setSelected(
                  checked ? [...selected, party.id] : selected.filter((id) => id !== party.id),
                )
              }
            >
              {party.acronym} — {party.name}
            </LabeledToggle>
          ))}
        </fieldset>
        <Button
          type="submit"
          disabled={create.isPending || selected.length < 2 || name.trim().length < 2}
        >
          Guardar
        </Button>
      </form>
    </FormDialog>
  );
}
