import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import {
  getPeaceSettingsOptions,
  listHouseGoalsOptions,
  listLevelGoalsOptions,
  listPrivacyNoticesOptions,
  publishPrivacyNoticeMutation,
  setHouseGoalMutation,
  setLevelGoalMutation,
  updatePeaceSettingsMutation,
} from "@/client/@tanstack/react-query.gen";
import type { LevelOut } from "@/client/types.gen";
import { AsyncCombobox, type ComboItem } from "@/components/async-combobox";
import { FormDialog } from "@/components/form-dialog";
import { PageHeader } from "@/components/page-header";
import { ProblemAlert } from "@/components/problem-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { SELECT_CLASS } from "@/features/peace-movement/labels";
import { useLevels } from "@/features/peace-movement/shared";
import { Perm } from "@/lib/auth/permissions";
import { useCan } from "@/lib/auth/use-me";
import { formatDate, formatDateTime } from "@/lib/labels";
import { GEO_SEARCH_HINTS, searchGeoItems } from "@/lib/search";

export const Route = createFileRoute("/_app/peace-movement/settings")({
  component: SettingsPage,
});

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

function SettingsPage() {
  const can = useCan();
  const editable = can(Perm.PEACE_GOAL_MANAGE);
  return (
    <section className="max-w-5xl">
      <PageHeader
        title="Configuración del Movimiento de Paz"
        description="Metas por estado con historial, semáforo, y avisos de privacidad. Cambiar una meta no reescribe el pasado."
      />
      <Tabs defaultValue="goals">
        <TabsList>
          <TabsTrigger value="goals">Metas de reclutamiento</TabsTrigger>
          <TabsTrigger value="houses">Metas de casas</TabsTrigger>
          <TabsTrigger value="settings">Semáforo</TabsTrigger>
          <TabsTrigger value="notices">Avisos de privacidad</TabsTrigger>
        </TabsList>
        <TabsContent value="goals">
          <LevelGoals editable={editable} />
        </TabsContent>
        <TabsContent value="houses">
          <HouseGoals editable={editable} />
        </TabsContent>
        <TabsContent value="settings">
          <TrafficSettings editable={editable} />
        </TabsContent>
        <TabsContent value="notices">
          <Notices editable={can(Perm.NOTICE_MANAGE)} />
        </TabsContent>
      </Tabs>
    </section>
  );
}

function StatePicker({
  value,
  onChange,
}: {
  value: ComboItem | null;
  onChange: (item: ComboItem | null) => void;
}) {
  return (
    <div className="grid w-72 gap-1.5">
      <Label htmlFor="goal-state">Estado (vacío = meta nacional)</Label>
      <AsyncCombobox
        id="goal-state"
        label="Nacional"
        value={value}
        onChange={onChange}
        queryKey={["goal-state"]}
        minChars={1}
        placeholder={GEO_SEARCH_HINTS.state}
        search={(term) => searchGeoItems(term, ["state"])}
      />
    </div>
  );
}

function LevelGoals({ editable }: { editable: boolean }) {
  const { levels } = useLevels();
  const [state, setState] = useState<ComboItem | null>(null);
  const goals = useQuery(
    listLevelGoalsOptions({ query: { ...(state ? { state_id: state.id } : {}), history: true } }),
  );
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Metas de reclutamiento por nivel</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <StatePicker value={state} onChange={setState} />
        <ProblemAlert error={goals.error} />
        <p className="text-xs text-muted-foreground">
          El avance se mide contra la meta vigente del estado del pacificador; si su estado no tiene
          una propia, contra la nacional. Las metas son acumuladas.
        </p>
        <div className="divide-y">
          {levels.map((level) => {
            const rows = (goals.data ?? []).filter(
              (g) => g.level_id === level.id && (g.state_id ?? null) === (state?.id ?? null),
            );
            const currentNational = (goals.data ?? []).find(
              (g) => g.level_id === level.id && !g.state_id && !g.valid_to,
            );
            return (
              <GoalRow
                key={level.id}
                level={level}
                stateId={state?.id ?? null}
                current={rows.find((g) => !g.valid_to)}
                national={currentNational}
                history={rows.filter((g) => g.valid_to)}
                editable={editable}
              />
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

function GoalRow({
  level,
  stateId,
  current,
  national,
  history,
  editable,
}: {
  level: LevelOut;
  stateId: string | null;
  current?: { recruit_goal: number; house_goal?: number | null; valid_from: string };
  national?: { recruit_goal: number; house_goal?: number | null };
  history: { recruit_goal: number; valid_from: string; valid_to?: string | null }[];
  editable: boolean;
}) {
  const queryClient = useQueryClient();
  const [recruits, setRecruits] = useState("");
  const [houses, setHouses] = useState("");
  const save = useMutation({
    ...setLevelGoalMutation(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [{ _id: "listLevelGoals" }] });
      setRecruits("");
      setHouses("");
      toast.success(`Meta de ${level.name} actualizada.`);
    },
  });
  const shown = current ?? (stateId ? undefined : national);
  return (
    <div className="grid gap-2 py-3 md:grid-cols-[12rem_1fr_auto] md:items-center">
      <div>
        <div className="font-medium">{level.name}</div>
        <div className="text-xs text-muted-foreground">
          {shown
            ? `${plural(shown.recruit_goal, "recluta", "reclutas")}${shown.house_goal ? ` · ${plural(shown.house_goal, "casa", "casas")}` : ""}${current ? ` desde ${formatDate(current.valid_from)}` : ""}`
            : `Usa la nacional: ${national ? plural(national.recruit_goal, "recluta", "reclutas") : "—"}`}
          {history.length ? ` · ${history.length} metas anteriores` : ""}
        </div>
      </div>
      {editable ? (
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate({
              body: {
                level_id: level.id,
                state_id: stateId,
                recruit_goal: Number(recruits),
                house_goal: houses ? Number(houses) : null,
              },
            });
          }}
        >
          <Input
            aria-label={`Nueva meta de reclutas de ${level.name}`}
            type="number"
            min={0}
            className="w-28"
            placeholder="Reclutas"
            value={recruits}
            onChange={(event) => setRecruits(event.target.value)}
          />
          {level.code === "peace_ambassador" ? (
            <Input
              aria-label="Nueva meta de casas consolidadas"
              type="number"
              min={0}
              className="w-24"
              placeholder="Casas"
              value={houses}
              onChange={(event) => setHouses(event.target.value)}
            />
          ) : null}
          <Button type="submit" size="sm" variant="outline" disabled={!recruits || save.isPending}>
            Fijar desde hoy
          </Button>
        </form>
      ) : (
        <span />
      )}
      <ProblemAlert error={save.error} />
    </div>
  );
}

function HouseGoals({ editable }: { editable: boolean }) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<ComboItem | null>(null);
  const [goal, setGoal] = useState("");
  const goals = useQuery(
    listHouseGoalsOptions({ query: { ...(state ? { state_id: state.id } : {}), history: true } }),
  );
  const save = useMutation({
    ...setHouseGoalMutation(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [{ _id: "listHouseGoals" }] });
      setGoal("");
      toast.success("Meta de integrantes actualizada.");
    },
  });
  const rows = (goals.data ?? []).filter((g) => (g.state_id ?? null) === (state?.id ?? null));
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Integrantes para consolidar una casa</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <StatePicker value={state} onChange={setState} />
        <ProblemAlert error={goals.error ?? save.error} />
        <ul className="text-sm">
          {rows.length ? (
            rows.map((g) => (
              <li key={g.id}>
                {g.member_goal} integrantes · desde {formatDate(g.valid_from)}
                {g.valid_to ? ` hasta ${formatDate(g.valid_to)}` : " (vigente)"}
              </li>
            ))
          ) : (
            <li className="text-muted-foreground">Sin meta propia: usa la nacional.</li>
          )}
        </ul>
        {editable ? (
          <form
            className="flex items-center gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              save.mutate({ body: { state_id: state?.id ?? null, member_goal: Number(goal) } });
            }}
          >
            <Input
              aria-label="Nueva meta de integrantes"
              type="number"
              min={1}
              className="w-32"
              value={goal}
              onChange={(event) => setGoal(event.target.value)}
            />
            <Button type="submit" size="sm" variant="outline" disabled={!goal || save.isPending}>
              Fijar desde hoy
            </Button>
          </form>
        ) : null}
      </CardContent>
    </Card>
  );
}

function TrafficSettings({ editable }: { editable: boolean }) {
  const queryClient = useQueryClient();
  const settings = useQuery(getPeaceSettingsOptions());
  const [draft, setDraft] = useState<Record<string, string>>({});
  const save = useMutation({
    ...updatePeaceSettingsMutation(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [{ _id: "getPeaceSettings" }] });
      setDraft({});
      toast.success("Configuración guardada.");
    },
  });
  const data = settings.data;
  if (!data) return <ProblemAlert error={settings.error} />;
  const value = (key: keyof typeof data) => draft[key] ?? String(data[key]);
  const fields: [keyof typeof data, string, string][] = [
    ["traffic_light_yellow_pct", "Amarillo desde (%)", "Por debajo, rojo"],
    ["traffic_light_green_pct", "Verde desde (%)", "Meta cumplida"],
    ["depth_alert_threshold", "Alerta de profundidad (niveles)", "Aviso operativo, no bloquea"],
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Semáforo de avance y alertas</h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate({
              body: {
                traffic_light_yellow_pct: Number(value("traffic_light_yellow_pct")),
                traffic_light_green_pct: Number(value("traffic_light_green_pct")),
                depth_alert_threshold: Number(value("depth_alert_threshold")),
              },
            });
          }}
        >
          <ProblemAlert error={save.error} />
          <div className="grid gap-3 md:grid-cols-3">
            {fields.map(([key, label, hint]) => (
              <div key={key} className="grid gap-1.5">
                <Label htmlFor={`setting-${key}`}>{label}</Label>
                <Input
                  id={`setting-${key}`}
                  type="number"
                  min={1}
                  value={value(key)}
                  disabled={!editable}
                  onChange={(event) => setDraft((d) => ({ ...d, [key]: event.target.value }))}
                />
                <p className="text-xs text-muted-foreground">{hint}</p>
              </div>
            ))}
          </div>
          {editable ? (
            <Button
              type="submit"
              className="justify-self-start"
              disabled={!Object.keys(draft).length || save.isPending}
            >
              Guardar
            </Button>
          ) : null}
        </form>
      </CardContent>
    </Card>
  );
}

const NOTICE_CODES: Record<string, string> = {
  peace_movement: "Aviso del Movimiento de Paz",
  peace_house_location: "Publicación de la ubicación de una casa",
  general: "Aviso general",
};

function Notices({ editable }: { editable: boolean }) {
  const queryClient = useQueryClient();
  const notices = useQuery(listPrivacyNoticesOptions({ query: {} }));
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("peace_movement");
  const [version, setVersion] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const publish = useMutation({
    ...publishPrivacyNoticeMutation(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [{ _id: "listPrivacyNotices" }] });
      setOpen(false);
      setVersion("");
      setTitle("");
      setBody("");
      toast.success("Aviso publicado; las nuevas inscripciones lo aceptan desde ahora.");
    },
  });
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>
          <h2>Avisos de privacidad</h2>
        </CardTitle>
        {editable ? (
          <FormDialog
            trigger={
              <Button size="sm" variant="outline">
                <Plus aria-hidden /> Publicar versión
              </Button>
            }
            title="Publicar una versión del aviso"
            description="El texto definitivo lo valida el área jurídica. La versión anterior queda en el catálogo."
            open={open}
            onOpenChange={setOpen}
            wide
          >
            <form
              className="grid gap-3"
              onSubmit={(event) => {
                event.preventDefault();
                publish.mutate({
                  body: { code, version: version.trim(), title: title.trim(), body: body.trim() },
                });
              }}
            >
              <ProblemAlert error={publish.error} />
              <div className="grid gap-3 md:grid-cols-[2fr_1fr]">
                <div className="grid gap-1.5">
                  <Label htmlFor="notice-code">Aviso</Label>
                  <select
                    id="notice-code"
                    className={SELECT_CLASS}
                    value={code}
                    onChange={(event) => setCode(event.target.value)}
                  >
                    {Object.entries(NOTICE_CODES).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="notice-version">Versión</Label>
                  <Input
                    id="notice-version"
                    value={version}
                    placeholder="2026-11"
                    onChange={(event) => setVersion(event.target.value)}
                  />
                </div>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="notice-title">Título</Label>
                <Input id="notice-title" value={title} onChange={(e) => setTitle(e.target.value)} />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="notice-body">Texto</Label>
                <Textarea
                  id="notice-body"
                  rows={10}
                  value={body}
                  onChange={(event) => setBody(event.target.value)}
                />
              </div>
              <Button
                type="submit"
                className="justify-self-start"
                disabled={
                  !version.trim() || !title.trim() || body.trim().length < 20 || publish.isPending
                }
              >
                Publicar
              </Button>
            </form>
          </FormDialog>
        ) : null}
      </CardHeader>
      <CardContent>
        <ProblemAlert error={notices.error} />
        <ul className="divide-y">
          {notices.data?.map((notice) => (
            <li key={notice.id} className="py-2 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{NOTICE_CODES[notice.code] ?? notice.code}</span>
                <Badge variant={notice.valid_to ? "outline" : "default"}>
                  {notice.valid_to ? "Anterior" : "Vigente"}
                </Badge>
                {notice.is_sample ? <Badge variant="destructive">Ejemplo, no válido</Badge> : null}
              </div>
              <div className="text-xs text-muted-foreground">
                Versión {notice.version} · desde {formatDateTime(notice.valid_from)} · huella{" "}
                <code>{notice.body_sha256.slice(0, 12)}…</code>
              </div>
            </li>
          ))}
        </ul>
        {notices.data?.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Sin avisos. Mientras no haya un aviso del MP vigente no se puede inscribir.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
