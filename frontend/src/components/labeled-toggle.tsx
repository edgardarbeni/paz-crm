import { useId } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

interface ToggleProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  children: React.ReactNode;
  className?: string;
  kind?: "checkbox" | "switch";
}

/** Checkbox or switch with an associated label (Radix toggles are buttons, so the label
 * points at them by id instead of wrapping them). */
export function LabeledToggle({
  checked,
  onCheckedChange,
  disabled,
  children,
  className,
  kind = "checkbox",
}: ToggleProps) {
  const id = useId();
  return (
    <div className={cn("flex items-start gap-2 text-sm", className)}>
      {kind === "switch" ? (
        <Switch id={id} checked={checked} disabled={disabled} onCheckedChange={onCheckedChange} />
      ) : (
        <Checkbox
          id={id}
          checked={checked}
          disabled={disabled}
          onCheckedChange={(c) => onCheckedChange(c === true)}
        />
      )}
      <Label htmlFor={id} className="font-normal leading-snug">
        {children}
      </Label>
    </div>
  );
}
