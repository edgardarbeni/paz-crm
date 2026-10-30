import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { listParticipationLevelsOptions } from "@/client/@tanstack/react-query.gen";
import { searchMembers, searchPeaceHouses } from "@/client/sdk.gen";
import type { LevelOut } from "@/client/types.gen";
import { AsyncCombobox, type ComboItem } from "@/components/async-combobox";
import { FormDialog } from "@/components/form-dialog";
import { ProblemAlert } from "@/components/problem-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  HOUSE_STATUS,
  HOUSE_STATUS_VARIANT,
  MEMBER_STATUS,
  MEMBER_STATUS_VARIANT,
  SELECT_CLASS,
  TRAFFIC_LIGHT,
} from "./labels";

/** Participation levels, ordered, with a lookup by id. */
export function useLevels() {
  const query = useQuery({ ...listParticipationLevelsOptions(), staleTime: 10 * 60_000 });
  const levels = query.data ?? [];
  const byId = new Map(levels.map((level) => [level.id, level]));
  return { levels, byId, isPending: query.isPending };
}

export function LevelSelect({
  id,
  value,
  onChange,
  levels,
  allowEmpty,
  emptyLabel = "Todos los niveles",
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  levels: LevelOut[];
  allowEmpty?: boolean;
  emptyLabel?: string;
}) {
  return (
    <select
      id={id}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className={SELECT_CLASS}
    >
      {allowEmpty ? <option value="">{emptyLabel}</option> : null}
      {levels.map((level) => (
        <option key={level.id} value={level.id}>
          {level.name}
        </option>
      ))}
    </select>
  );
}

export function MemberStatusBadge({ status }: { status: string }) {
  return (
    <Badge variant={MEMBER_STATUS_VARIANT[status] ?? "outline"}>
      {MEMBER_STATUS[status] ?? status}
    </Badge>
  );
}

export function HouseStatusBadge({ status }: { status: string }) {
  return (
    <Badge variant={HOUSE_STATUS_VARIANT[status] ?? "outline"}>
      {HOUSE_STATUS[status] ?? status}
    </Badge>
  );
}

export function TrafficLight({ light }: { light: string | null | undefined }) {
  const meta = light ? TRAFFIC_LIGHT[light] : undefined;
  if (!meta) return null;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1",
        meta.className,
      )}
    >
      <span aria-hidden className="size-2 rounded-full bg-current" />
      {meta.label}
    </span>
  );
}

/** Progress against a goal: a bar capped at 100 % with the exact figures as text. */
export function GoalProgress({
  label,
  current,
  goal,
  pct,
}: {
  label: string;
  current: number;
  goal: number | null | undefined;
  pct: number | null | undefined;
}) {
  if (goal == null || pct == null) {
    return <p className="text-sm text-muted-foreground">{label}: sin meta vigente.</p>;
  }
  return (
    <div className="grid gap-1.5">
      <div className="flex items-baseline justify-between text-sm">
        <span>{label}</span>
        <span className="tabular-nums">
          <strong>{current}</strong> de {goal} · {pct} %
        </span>
      </div>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.min(pct, 100)}
        className="h-2 overflow-hidden rounded-full bg-muted"
      >
        <div
          className="h-full rounded-full bg-primary transition-[width]"
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
    </div>
  );
}

/** Autocomplete of members (by name), optionally only active ones. */
export function MemberPicker({
  id,
  label,
  value,
  onChange,
  activeOnly = true,
}: {
  id: string;
  label: string;
  value: ComboItem | null;
  onChange: (item: ComboItem | null) => void;
  activeOnly?: boolean;
}) {
  return (
    <AsyncCombobox
      id={id}
      label={label}
      value={value}
      onChange={onChange}
      queryKey={["member-picker", activeOnly]}
      placeholder="Nombre del pacificador"
      search={async (term) => {
        const { data } = await searchMembers({
          query: { q: term, limit: 20, ...(activeOnly ? { status: "active" } : {}) },
          throwOnError: true,
        });
        return data.items.map((member) => ({
          id: member.id,
          label: member.person.full_name,
          hint: MEMBER_STATUS[member.status] ?? member.status,
        }));
      }}
    />
  );
}

export function HousePicker({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: ComboItem | null;
  onChange: (item: ComboItem | null) => void;
}) {
  return (
    <AsyncCombobox
      id={id}
      label={label}
      value={value}
      onChange={onChange}
      queryKey={["house-picker"]}
      minChars={0}
      placeholder="Casas abiertas o consolidadas"
      search={async (term) => {
        const { data } = await searchPeaceHouses({ query: { limit: 50 }, throwOnError: true });
        const needle = term.trim().toLowerCase();
        return data.items
          .filter((house) => house.status !== "closed")
          .filter((house) => !needle || house.name.toLowerCase().includes(needle))
          .map((house) => ({
            id: house.id,
            label: house.name,
            hint: `${HOUSE_STATUS[house.status]} · ${house.member_count} integrantes`,
          }));
      }}
    />
  );
}

/** A dialog that asks for a reason before an action (reject, leave, close…). */
export function ReasonDialog({
  trigger,
  title,
  description,
  confirmLabel,
  onConfirm,
  error,
  pending,
  destructive,
}: {
  trigger: React.ReactNode;
  title: string;
  description?: string;
  confirmLabel: string;
  onConfirm: (reason: string) => Promise<unknown>;
  error: unknown;
  pending: boolean;
  destructive?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  return (
    <FormDialog
      trigger={trigger}
      title={title}
      description={description}
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setReason("");
      }}
    >
      <form
        className="grid gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          onConfirm(reason.trim())
            .then(() => setOpen(false))
            .catch(() => {});
        }}
      >
        <ProblemAlert error={error} />
        <div className="grid gap-1.5">
          <Label htmlFor="reason">Motivo</Label>
          <Textarea
            id="reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            minLength={3}
            maxLength={500}
            required
          />
        </div>
        <Button
          type="submit"
          variant={destructive ? "destructive" : "default"}
          disabled={reason.trim().length < 3 || pending}
          className="justify-self-start"
        >
          {pending ? "Guardando…" : confirmLabel}
        </Button>
      </form>
    </FormDialog>
  );
}

/** Label/value list used in the detail cards. */
export function Facts({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt className="text-xs text-muted-foreground">{label}</dt>
          <dd className="text-sm">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
