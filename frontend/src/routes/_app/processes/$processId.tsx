import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import {
  getProcessOptions,
  getProcessQueryKey,
  updateProcessMutation,
} from "@/client/@tanstack/react-query.gen";
import type { ProcessStatus } from "@/client/types.gen";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { GeoName } from "@/features/candidacies/geo-name";
import { CoalitionsTab } from "@/features/candidacies/process/coalitions-tab";
import { MunicipalitiesTab } from "@/features/candidacies/process/municipalities-tab";
import { OfficesTab } from "@/features/candidacies/process/offices-tab";
import { RulesTab } from "@/features/candidacies/process/rules-tab";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";
import { ELECTION_LEVEL, formatDate, PROCESS_STATUS } from "@/lib/labels";

export const Route = createFileRoute("/_app/processes/$processId")({ component: ProcessPage });

function ProcessPage() {
  const { processId } = Route.useParams();
  const can = useCan();
  const queryClient = useQueryClient();
  const process = useQuery(getProcessOptions({ path: { process_id: processId } }));
  const update = useMutation({
    ...updateProcessMutation(),
    onSuccess: (data) =>
      queryClient.setQueryData(getProcessQueryKey({ path: { process_id: processId } }), data),
  });
  if (process.isError) return <ProblemAlert error={process.error} />;
  const p = process.data;
  if (!p) return <p className="text-muted-foreground">Cargando…</p>;
  const editable = can(Perm.PROCESS_MANAGE) && p.status !== "closed";

  return (
    <section>
      <PageHeader
        title={p.name}
        description={
          <>
            {ELECTION_LEVEL[p.election_level]} {p.election_year}
            {p.state_id ? (
              <>
                {" · "}
                <GeoName level="state" id={p.state_id} />
              </>
            ) : null}
            {` · Jornada: ${formatDate(p.election_date)}`}
          </>
        }
        actions={
          <>
            <Badge variant="secondary">{PROCESS_STATUS[p.status]}</Badge>
            {can(Perm.PROCESS_MANAGE) ? (
              <select
                aria-label="Cambiar estatus del proceso"
                value={p.status}
                onChange={(e) =>
                  update.mutate({
                    path: { process_id: processId },
                    body: { status: e.target.value as ProcessStatus },
                  })
                }
                className="h-8 rounded-lg border border-input bg-transparent px-2 text-sm"
              >
                {Object.entries(PROCESS_STATUS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            ) : null}
            <Button asChild variant="outline">
              <Link to="/nominations" search={{ process_id: processId }}>
                Ver postulaciones
              </Link>
            </Button>
          </>
        }
      />
      <ProblemAlert error={update.error} />
      <Tabs defaultValue="offices">
        <TabsList>
          <TabsTrigger value="offices">Cargos</TabsTrigger>
          {p.state_id ? <TabsTrigger value="municipalities">Municipios</TabsTrigger> : null}
          <TabsTrigger value="rules">Reglas</TabsTrigger>
          <TabsTrigger value="coalitions">Coaliciones</TabsTrigger>
        </TabsList>
        <TabsContent value="offices" className="pt-4">
          <OfficesTab processId={processId} editable={editable} />
        </TabsContent>
        {p.state_id ? (
          <TabsContent value="municipalities" className="pt-4">
            <MunicipalitiesTab processId={processId} stateId={p.state_id} editable={editable} />
          </TabsContent>
        ) : null}
        <TabsContent value="rules" className="pt-4">
          <RulesTab processId={processId} editable={editable} />
        </TabsContent>
        <TabsContent value="coalitions" className="pt-4">
          <CoalitionsTab processId={processId} editable={editable} />
        </TabsContent>
      </Tabs>
    </section>
  );
}
