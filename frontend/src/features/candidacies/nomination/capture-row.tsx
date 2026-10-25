import { UserPlus } from "lucide-react";
import { useState } from "react";
import type { Override } from "@/client/types.gen";
import { AsyncCombobox, type ComboItem } from "@/components/async-combobox";
import { Button } from "@/components/ui/button";
import { QuickPersonDialog } from "@/features/people/quick-person-dialog";
import { searchPeopleItems } from "@/lib/search";

export interface MembersValue {
  owner: ComboItem | null;
  substitute: ComboItem | null;
}

/**
 * One position of a slate/list in capture mode: owner → substitute → Guardar, all with the
 * keyboard. Ctrl+Enter saves from any control of the row; "+" opens the quick person form.
 */
export function CaptureRow({
  rowId,
  label,
  hasSubstitute,
  initial,
  onSave,
  onCancel,
  saveLabel = "Guardar",
}: {
  rowId: string;
  label: string;
  hasSubstitute: boolean;
  initial?: MembersValue;
  onSave: (value: MembersValue, override?: Override) => Promise<unknown>;
  onCancel?: () => void;
  saveLabel?: string;
}) {
  const [value, setValue] = useState<MembersValue>(initial ?? { owner: null, substitute: null });
  const [creatingFor, setCreatingFor] = useState<keyof MembersValue | null>(null);
  const [busy, setBusy] = useState(false);
  const ready = !!value.owner && (!hasSubstitute || !!value.substitute);

  async function save() {
    if (!ready || busy) return;
    setBusy(true);
    try {
      await onSave(value);
    } finally {
      setBusy(false);
    }
  }

  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: keyboard shortcut container for the row's controls
    <div
      className="grid items-center gap-2 md:grid-cols-[1fr_1fr_auto]"
      onKeyDown={(event) => {
        if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
          event.preventDefault();
          save();
        }
      }}
    >
      {(["owner", "substitute"] as const).map((role) =>
        role === "substitute" && !hasSubstitute ? (
          <span key={role} className="text-xs text-muted-foreground">
            Sin suplencia
          </span>
        ) : (
          <div key={role} className="flex items-center gap-1">
            <AsyncCombobox
              id={role === "owner" ? `capture-${rowId}` : undefined}
              label={`${role === "owner" ? "Propietaria" : "Suplente"} · ${label}`}
              value={value[role]}
              onChange={(item) => setValue((v) => ({ ...v, [role]: item }))}
              queryKey={["people-search"]}
              search={searchPeopleItems}
              className="flex-1"
            />
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={`Registrar nueva persona como ${role === "owner" ? "propietaria" : "suplente"}`}
              onClick={() => setCreatingFor(role)}
            >
              <UserPlus aria-hidden />
            </Button>
          </div>
        ),
      )}
      <div className="flex gap-1">
        <Button type="button" size="sm" onClick={save} disabled={!ready || busy}>
          {busy ? "Guardando…" : saveLabel}
        </Button>
        {onCancel ? (
          <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
            Cancelar
          </Button>
        ) : null}
      </div>
      <QuickPersonDialog
        open={creatingFor !== null}
        onClose={() => setCreatingFor(null)}
        onCreated={(item) => creatingFor && setValue((v) => ({ ...v, [creatingFor]: item }))}
      />
    </div>
  );
}
