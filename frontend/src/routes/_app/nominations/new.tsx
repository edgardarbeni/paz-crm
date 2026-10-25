import { useMutation, useQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { z } from "zod";
import {
  createNominationMutation,
  listCoalitionsOptions,
  listProcessOfficesOptions,
} from "@/client/@tanstack/react-query.gen";
import { AsyncCombobox, type ComboItem } from "@/components/async-combobox";
import { FieldShell } from "@/components/form/form";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { useCatalogs } from "@/features/candidacies/use-catalogs";
import { GEO_LEVEL_LABELS } from "@/lib/labels";
import { GEO_SEARCH_HINTS, type GeoSearchLevel, searchGeoItems } from "@/lib/search";

export const Route = createFileRoute("/_app/nominations/new")({
  validateSearch: z.object({ process_id: z.string().optional() }),
  component: NewNominationPage,
});

const selectClass = "h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm";

function NewNominationPage() {
  const initial = Route.useSearch();
  const navigate = useNavigate();
  const { processes, officeById, parties } = useCatalogs();
  const [processId, setProcessId] = useState(initial.process_id ?? "");
  const [officeId, setOfficeId] = useState("");
  const [node, setNode] = useState<ComboItem | null>(null);
  const [nominator, setNominator] = useState<"party" | "coalition">("party");
  const [nominatorId, setNominatorId] = useState("");
  const [notes, setNotes] = useState("");
  const configs = useQuery({
    ...listProcessOfficesOptions({ path: { process_id: processId } }),
    enabled: !!processId,
  });
  const coalitions = useQuery({
    ...listCoalitionsOptions({ path: { process_id: processId } }),
    enabled: !!processId,
  });
  const create = useMutation({
    ...createNominationMutation(),
    onSuccess: (nomination) =>
      navigate({ to: "/nominations/$nominationId", params: { nominationId: nomination.id } }),
  });
  const available = (configs.data ?? []).filter(
    (c) =>
      c.is_enabled &&
      !c.slate_parent_office_type_id &&
      officeById.get(c.office_type_id)?.nomination_kind !== "member",
  );
  const office = officeById.get(officeId);
  const level = office?.geographic_level;
  const needsNode = !!level && level !== "national";

  return (
    <section className="max-w-2xl">
      <PageHeader
        title="Nueva postulación"
        description="Elige el proceso, el cargo, la geografía y quién postula."
      />
      <Card>
        <CardContent>
          <form
            className="grid gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              create.mutate({
                body: {
                  process_id: processId,
                  office_type_id: officeId,
                  node_id: needsNode ? node?.id : null,
                  party_id: nominator === "party" ? nominatorId : null,
                  coalition_id: nominator === "coalition" ? nominatorId : null,
                  notes: notes.trim() || null,
                },
              });
            }}
          >
            <ProblemAlert error={create.error} />
            <FieldShell id="nomination-process" label="Proceso electoral" required>
              <select
                id="nomination-process"
                className={selectClass}
                value={processId}
                onChange={(e) => {
                  setProcessId(e.target.value);
                  setOfficeId("");
                  setNode(null);
                  setNominatorId("");
                }}
              >
                <option value="">Selecciona…</option>
                {processes
                  .filter((p) => p.status !== "closed")
                  .map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
              </select>
            </FieldShell>
            <FieldShell
              id="nomination-office"
              label="Cargo"
              required
              description={
                processId && !available.length
                  ? "El proceso no tiene cargos habilitados."
                  : undefined
              }
            >
              <select
                id="nomination-office"
                className={selectClass}
                value={officeId}
                disabled={!processId}
                onChange={(e) => {
                  setOfficeId(e.target.value);
                  setNode(null);
                }}
              >
                <option value="">Selecciona…</option>
                {available.map((c) => (
                  <option key={c.office_type_id} value={c.office_type_id}>
                    {c.office_name}
                  </option>
                ))}
              </select>
            </FieldShell>
            {needsNode ? (
              <FieldShell
                id="nomination-node"
                label={GEO_LEVEL_LABELS[level] ?? "Geografía"}
                required
              >
                <AsyncCombobox
                  id="nomination-node"
                  label={`Buscar ${GEO_LEVEL_LABELS[level]?.toLowerCase()}`}
                  value={node}
                  onChange={setNode}
                  queryKey={["geo-search", level]}
                  search={(term) => searchGeoItems(term, [level as GeoSearchLevel])}
                  minChars={1}
                  placeholder={GEO_SEARCH_HINTS[level]}
                />
              </FieldShell>
            ) : null}
            <fieldset className="grid gap-2">
              <legend className="text-sm font-medium">Postula</legend>
              <div className="flex gap-4 text-sm">
                {(["party", "coalition"] as const).map((kind) => (
                  <label key={kind} className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="nominator"
                      checked={nominator === kind}
                      onChange={() => {
                        setNominator(kind);
                        setNominatorId("");
                      }}
                    />
                    {kind === "party" ? "Partido" : "Coalición o candidatura común"}
                  </label>
                ))}
              </div>
              <select
                aria-label={nominator === "party" ? "Partido que postula" : "Coalición que postula"}
                className={selectClass}
                value={nominatorId}
                onChange={(e) => setNominatorId(e.target.value)}
              >
                <option value="">Selecciona…</option>
                {nominator === "party"
                  ? parties.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.acronym} — {p.name}
                      </option>
                    ))
                  : (coalitions.data ?? []).map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
              </select>
            </fieldset>
            <FieldShell id="nomination-notes" label="Notas">
              <Textarea
                id="nomination-notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                maxLength={2000}
              />
            </FieldShell>
            <Button
              type="submit"
              disabled={
                create.isPending || !processId || !officeId || !nominatorId || (needsNode && !node)
              }
            >
              {create.isPending ? "Creando…" : "Crear y capturar fórmulas"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </section>
  );
}
