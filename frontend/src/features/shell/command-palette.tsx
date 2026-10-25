import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import type { NavSection } from "@/features/shell/nav";
import { useHotkey } from "@/hooks/use-hotkey";

/** Ctrl/⌘+K: jump to any screen by name. */
export function CommandPalette({ sections }: { sections: NavSection[] }) {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  useHotkey("mod+k", () => setOpen((value) => !value));
  return (
    <CommandDialog
      open={open}
      onOpenChange={setOpen}
      title="Ir a…"
      description="Busca una pantalla"
    >
      {/* The shadcn dialog does not provide the cmdk root itself. */}
      <Command>
        <CommandInput placeholder="Ir a…" />
        <CommandList>
          <CommandEmpty>Sin coincidencias.</CommandEmpty>
          {sections.map((section) => (
            <CommandGroup key={section.label} heading={section.label}>
              {section.items.map((item) => (
                <CommandItem
                  key={item.to}
                  value={`${section.label} ${item.label}`}
                  onSelect={() => {
                    setOpen(false);
                    navigate({ to: item.to });
                  }}
                >
                  <item.icon aria-hidden />
                  {item.label}
                </CommandItem>
              ))}
            </CommandGroup>
          ))}
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
