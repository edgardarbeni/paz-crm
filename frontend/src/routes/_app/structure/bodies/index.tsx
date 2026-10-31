import { useMutation, useQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import {
  getStructureCatalogOptions,
  installBodyMutation,
  listBodiesOptions,
} from "@/client/@tanstack/react-query.gen";
import type { BodyOut } from "@/client/types.gen";
import { AsyncCombobox, type ComboItem } from "@/components/async-combobox";
import { type Column, DataTable } from "@/components/data/data-table";
import { useCursorPager } from "@/components/data/use-cursor-pager";
import { FormDialog } from "@/components/form-dialog";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LEVEL, STATE_CODES } from "@/features/party-structure/labels";
import { SELECT_CLASS } from "@/features/peace-movement/labels";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";
import { formatDate } from "@/lib/labels";
import { searchGeoItems } from "@/lib/search";

const LEVELS = ["national", "state", "district", "municipal"] as const;

export const Route = createFileRoute("/_app/structure/bodies/")({
  validateSearch: z.object({
    level: z.enum(LEVELS).optional(),
    state: z.number().int().min(1).max(32).optional(),
    dissolved: z.boolean().optional(),
  }),
  component: BodiesPage,
});

const columns: Column<BodyOut>[] = [
  {
    id: "type",
    header: "Órgano",
    cell: ({ row }) => <span className="font-medium">{row.original.body_type.name}</span>,
  },
  { id: "territory", header: "Territorio", cell: ({ row }) => row.original.territory },
  {
    id: "level",
    header: "Nivel",
    cell: ({ row }) => LEVEL[row.original.body_type.territorial_level],
  },
  {
    id: "status",
    header: "Estatus",
    cell: ({ row }) =>
      row.original.status === "dissolved" ? (
        <Badge variant="secondary">Disuelto {formatDate(row.original.dissolved_on)}</Badge>
      ) : row.original.installed_on ? (
        `Instalado ${formatDate(row.original.installed_on)}`
      ) : (
        "Instalado"
      ),
  },
];

/** Bodies of the party structure inside the user's scope (D-107): national and state ones are
 * permanent; district and municipal committees exist from their installation. */
function BodiesPage() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const can = useCan();
  const query = {
    ...(search.level ? { level: search.level } : {}),
    ...(search.state ? { state_code: search.state } : {}),
    ...(search.dissolved ? { include_dissolved: true } : {}),
  };
  const { cursor, pager } = useCursorPager(JSON.stringify(query));
  const bodies = useQuery(listBodiesOptions({ query: { ...query, cursor, limit: 50 } }));
  return (
    <section>
      <PageHeader
        title="Órganos y cargos"
        description="Órganos del estatuto en tu alcance. Abre uno para ver sus cargos, nombrar y dar acceso."
        actions={can(Perm.STRUCTURE_BODY_WRITE) ? <InstallCommittee /> : null}
      />
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="grid gap-1.5">
          <Label htmlFor="body-level">Nivel</Label>
          <select
            id="body-level"
            className={SELECT_CLASS}
            value={search.level ?? ""}
            onChange={(e) =>
              navigate({
                search: (prev) => ({
                  ...prev,
                  level: (e.target.value || undefined) as (typeof LEVELS)[number],
                }),
              })
            }
          >
            <option value="">Todos</option>
            {LEVELS.map((level) => (
              <option key={level} value={level}>
                {LEVEL[level]}
              </option>
            ))}
          </select>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="body-state">Estado (clave INE)</Label>
          <select
            id="body-state"
            className={SELECT_CLASS}
            value={search.state ?? ""}
            onChange={(e) =>
              navigate({
                search: (prev) => ({
                  ...prev,
                  state: e.target.value ? Number(e.target.value) : undefined,
                }),
              })
            }
          >
            <option value="">Todos</option>
            {STATE_CODES.map((code) => (
              <option key={code} value={code}>
                {String(code).padStart(2, "0")}
              </option>
            ))}
          </select>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={!!search.dissolved}
            onChange={(e) =>
              navigate({
                search: (prev) => ({ ...prev, dissolved: e.target.checked || undefined }),
              })
            }
          />
          Incluir disueltos
        </label>
      </div>
      <ProblemAlert error={bodies.error} />
      <DataTable
        caption="Órganos"
        columns={columns}
        data={bodies.data?.items}
        isLoading={bodies.isPending}
        getRowId={(row) => row.id}
        pager={pager(bodies.data)}
        onActivate={(row) =>
          navigate({ to: "/structure/bodies/$bodyId", params: { bodyId: row.id } })
        }
        empty="No hay órganos con estos filtros."
      />
    </section>
  );
}

function InstallCommittee() {
  const navigate = useNavigate();
  const catalog = useQuery(getStructureCatalogOptions());
  const [open, setOpen] = useState(false);
  const [typeId, setTypeId] = useState("");
  const [district, setDistrict] = useState<"federal_district" | "local_district">(
    "federal_district",
  );
  const [node, setNode] = useState<ComboItem | null>(null);
  const [installedOn, setInstalledOn] = useState(new Date().toISOString().slice(0, 10));
  const [agreement, setAgreement] = useState("");
  const types = (catalog.data ?? []).filter((t) => t.requires_installation && !t.coordination_kind);
  const chosen = types.find((t) => t.id === typeId);
  const nodeLevel = chosen?.territorial_level === "municipal" ? "municipality" : district;
  const install = useMutation({
    ...installBodyMutation(),
    onSuccess: (body) => {
      toast.success(`${body.body_type.name} instalado.`);
      setOpen(false);
      navigate({ to: "/structure/bodies/$bodyId", params: { bodyId: body.id } });
    },
  });
  return (
    <FormDialog
      trigger={
        <Button>
          <Plus aria-hidden /> Instalar comité
        </Button>
      }
      title="Registrar la instalación de un comité"
      description="Comités distritales (federal o local) y municipales, por acuerdo del CDN. Sus cargos se crean al instalarlo."
      open={open}
      onOpenChange={setOpen}
    >
      <form
        className="grid gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (!chosen || !node) return;
          install.mutate({
            body: {
              body_type_id: chosen.id,
              [`${nodeLevel}_id`]: node.id,
              installed_on: installedOn,
              installation_agreement: agreement.trim(),
            },
          });
        }}
      >
        <ProblemAlert error={install.error} />
        <div className="grid gap-1.5">
          <Label htmlFor="install-type">Comité</Label>
          <select
            id="install-type"
            className={SELECT_CLASS}
            value={typeId}
            onChange={(e) => {
              setTypeId(e.target.value);
              setNode(null);
            }}
          >
            <option value="">Elige…</option>
            {types.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
        {chosen?.territorial_level === "district" ? (
          <div className="grid gap-1.5">
            <Label htmlFor="install-district">Tipo de distrito</Label>
            <select
              id="install-district"
              className={SELECT_CLASS}
              value={district}
              onChange={(e) => {
                setDistrict(e.target.value as typeof district);
                setNode(null);
              }}
            >
              <option value="federal_district">Distrito federal</option>
              <option value="local_district">Distrito local</option>
            </select>
          </div>
        ) : null}
        {chosen ? (
          <div className="grid gap-1.5">
            <Label htmlFor="install-node">Territorio</Label>
            <AsyncCombobox
              id="install-node"
              label="Territorio"
              value={node}
              onChange={setNode}
              queryKey={["install-node", nodeLevel]}
              search={(term) => searchGeoItems(term, [nodeLevel])}
              minChars={1}
              placeholder="Nombre o número"
            />
          </div>
        ) : null}
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="grid gap-1.5">
            <Label htmlFor="install-date">Fecha de instalación</Label>
            <Input
              id="install-date"
              type="date"
              value={installedOn}
              onChange={(e) => setInstalledOn(e.target.value)}
              required
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="install-agreement">Acuerdo del CDN</Label>
            <Input
              id="install-agreement"
              value={agreement}
              onChange={(e) => setAgreement(e.target.value)}
              required
              minLength={2}
            />
          </div>
        </div>
        <Button
          type="submit"
          className="justify-self-start"
          disabled={!chosen || !node || agreement.trim().length < 2 || install.isPending}
        >
          Instalar
        </Button>
      </form>
    </FormDialog>
  );
}
