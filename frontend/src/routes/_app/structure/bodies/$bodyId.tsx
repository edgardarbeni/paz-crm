import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { dissolveBodyMutation, getBodyOptions } from "@/client/@tanstack/react-query.gen";
import { FormDialog } from "@/components/form-dialog";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LEVEL } from "@/features/party-structure/labels";
import { SeatsPanel } from "@/features/party-structure/seats";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";
import { formatDate } from "@/lib/labels";

export const Route = createFileRoute("/_app/structure/bodies/$bodyId")({ component: BodyPage });

function BodyPage() {
  const { bodyId } = Route.useParams();
  const can = useCan();
  const body = useQuery(getBodyOptions({ path: { body_id: bodyId } }));
  if (body.isError) return <ProblemAlert error={body.error} />;
  const b = body.data;
  if (!b) return <p className="text-muted-foreground">Cargando…</p>;
  const committee =
    b.body_type.territorial_level === "district" || b.body_type.territorial_level === "municipal";
  return (
    <section className="max-w-4xl space-y-6">
      <PageHeader
        title={b.body_type.name}
        description={`${b.territory} · ${LEVEL[b.body_type.territorial_level]}${
          b.installed_on ? ` · instalado ${formatDate(b.installed_on)}` : ""
        }${b.installation_agreement ? ` (${b.installation_agreement})` : ""}`}
        actions={
          b.status === "dissolved" ? (
            <Badge variant="secondary">Disuelto {formatDate(b.dissolved_on)}</Badge>
          ) : committee && can(Perm.STRUCTURE_BODY_WRITE) ? (
            <Dissolve bodyId={b.id} />
          ) : null
        }
      />
      <Card>
        <CardHeader>
          <CardTitle>
            <h2>Cargos</h2>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <SeatsPanel bodyId={b.id} dissolved={b.status === "dissolved"} />
        </CardContent>
      </Card>
    </section>
  );
}

function Dissolve({ bodyId }: { bodyId: string }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [on, setOn] = useState(new Date().toISOString().slice(0, 10));
  const [agreement, setAgreement] = useState("");
  const dissolve = useMutation({
    ...dissolveBodyMutation(),
    onSuccess: (data) => {
      queryClient.setQueryData(getBodyOptions({ path: { body_id: bodyId } }).queryKey, data);
      queryClient.invalidateQueries({ queryKey: [{ _id: "listBodies" }] });
      setOpen(false);
      toast.success("Comité disuelto.");
    },
  });
  return (
    <FormDialog
      trigger={<Button variant="outline">Disolver</Button>}
      title="Registrar la disolución del comité"
      open={open}
      onOpenChange={setOpen}
    >
      <form
        className="grid gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          dissolve.mutate({
            path: { body_id: bodyId },
            body: { dissolved_on: on, dissolution_agreement: agreement.trim() },
          });
        }}
      >
        <ProblemAlert error={dissolve.error} />
        <div className="grid gap-1.5">
          <Label htmlFor="dissolve-date">Fecha</Label>
          <Input
            id="dissolve-date"
            type="date"
            value={on}
            onChange={(e) => setOn(e.target.value)}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="dissolve-agreement">Acuerdo</Label>
          <Input
            id="dissolve-agreement"
            value={agreement}
            onChange={(e) => setAgreement(e.target.value)}
            required
            minLength={2}
          />
        </div>
        <Button
          type="submit"
          className="justify-self-start"
          disabled={agreement.trim().length < 2 || dissolve.isPending}
        >
          Disolver
        </Button>
      </form>
    </FormDialog>
  );
}
