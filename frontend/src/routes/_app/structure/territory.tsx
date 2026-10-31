import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import {
  listTerritoryIssuesOptions,
  resolveTerritoryIssueMutation,
} from "@/client/@tanstack/react-query.gen";
import type { TerritoryIssueOut } from "@/client/types.gen";
import { AsyncCombobox, type ComboItem } from "@/components/async-combobox";
import { FormDialog } from "@/components/form-dialog";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ISSUE_KIND } from "@/features/party-structure/labels";
import { formatDate } from "@/lib/labels";
import { searchGeoItems } from "@/lib/search";

export const Route = createFileRoute("/_app/structure/territory")({ component: TerritoryPage });

/** Tray after activating a new framework (D-102, D-111): what had no equivalent. National
 * level only. */
function TerritoryPage() {
  const issues = useQuery(listTerritoryIssuesOptions({ query: {} }));
  return (
    <section className="max-w-4xl space-y-4">
      <PageHeader
        title="Territorio por resolver"
        description="Lo que no tuvo equivalente al activar un marco geográfico nuevo. El resto se remapeó solo."
      />
      <ProblemAlert error={issues.error} />
      {issues.data?.length === 0 ? (
        <p className="text-sm text-muted-foreground">No hay pendientes.</p>
      ) : null}
      {(issues.data ?? []).map((issue) => (
        <Card key={issue.id}>
          <CardContent className="space-y-2 text-sm">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <div>
                <div className="font-medium">{ISSUE_KIND[issue.kind]}</div>
                <Link
                  to="/structure/bodies/$bodyId"
                  params={{ bodyId: issue.body.id }}
                  className="underline-offset-4 hover:underline"
                >
                  {issue.body.body_type.name} · {issue.body.territory}
                </Link>
              </div>
              <span className="text-xs text-muted-foreground">
                Detectado {formatDate(issue.detected_on)}
              </span>
            </div>
            <p className="text-muted-foreground">
              Sin equivalente: {issue.lost.map((l) => l.label).join(", ")}
            </p>
            <Resolve issue={issue} />
          </CardContent>
        </Card>
      ))}
    </section>
  );
}

function Resolve({ issue }: { issue: TerritoryIssueOut }) {
  const queryClient = useQueryClient();
  const committee = issue.kind === "committee_without_territory";
  const [open, setOpen] = useState<null | "reassign" | "dissolve" | "accept" | "close">(null);
  const [node, setNode] = useState<ComboItem | null>(null);
  const [notes, setNotes] = useState("");
  const resolve = useMutation({
    ...resolveTerritoryIssueMutation(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [{ _id: "listTerritoryIssues" }] });
      setOpen(null);
      toast.success("Pendiente resuelto.");
    },
  });
  const level =
    issue.body.municipality_id !== null
      ? "municipality"
      : issue.body.district_kind === "federal"
        ? "federal_district"
        : "local_district";
  const actions = committee
    ? ([
        ["reassign", "Reasignar territorio"],
        ["dissolve", "Disolver"],
      ] as const)
    : ([
        ["accept", "Aceptar como quedó"],
        ["close", "Cerrar la coordinación"],
      ] as const);
  return (
    <div className="flex flex-wrap gap-2">
      {actions.map(([action, label]) => (
        <FormDialog
          key={action}
          trigger={
            <Button size="sm" variant="outline">
              {label}
            </Button>
          }
          title={label}
          description={
            action === "dissolve" || action === "close"
              ? "Termina sus nombramientos vigentes y retira su acceso."
              : undefined
          }
          open={open === action}
          onOpenChange={(value) => setOpen(value ? action : null)}
        >
          <form
            className="grid gap-3"
            onSubmit={(event) => {
              event.preventDefault();
              resolve.mutate({
                path: { issue_id: issue.id },
                body: {
                  action,
                  node_id: action === "reassign" ? (node?.id ?? null) : null,
                  on: new Date().toISOString().slice(0, 10),
                  notes: notes.trim() || null,
                },
              });
            }}
          >
            <ProblemAlert error={resolve.error} />
            {action === "reassign" ? (
              <div className="grid gap-1.5">
                <Label htmlFor={`node-${issue.id}`}>Territorio en el marco activo</Label>
                <AsyncCombobox
                  id={`node-${issue.id}`}
                  label="Territorio"
                  value={node}
                  onChange={setNode}
                  queryKey={["issue-node", level]}
                  search={(term) => searchGeoItems(term, [level])}
                  minChars={1}
                />
              </div>
            ) : null}
            <div className="grid gap-1.5">
              <Label htmlFor={`notes-${issue.id}-${action}`}>Notas o acuerdo</Label>
              <Input
                id={`notes-${issue.id}-${action}`}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </div>
            <Button
              type="submit"
              className="justify-self-start"
              disabled={(action === "reassign" && !node) || resolve.isPending}
            >
              Confirmar
            </Button>
          </form>
        </FormDialog>
      ))}
    </div>
  );
}
