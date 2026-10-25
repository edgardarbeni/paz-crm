import { useQuery } from "@tanstack/react-query";
import { Check, ChevronsUpDown, X } from "lucide-react";
import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useDebounced } from "@/hooks/use-debounced";
import { cn } from "@/lib/utils";

export interface ComboItem {
  id: string;
  label: string;
  hint?: string;
}

interface AsyncComboboxProps {
  /** Accessible name (also shown as placeholder when empty). */
  label: string;
  value: ComboItem | null;
  onChange: (item: ComboItem | null) => void;
  /** Distinguishes cached searches of different comboboxes. */
  queryKey: readonly unknown[];
  search: (term: string) => Promise<ComboItem[]>;
  minChars?: number;
  disabled?: boolean;
  invalid?: boolean;
  id?: string;
  className?: string;
  emptyText?: string;
}

/**
 * Keyboard-first autocomplete against the API: focus it and start typing (the popover opens
 * with the first key), ↑/↓ to move, Enter to pick, Esc to close, Supr to clear.
 */
export function AsyncCombobox({
  label,
  value,
  onChange,
  queryKey,
  search,
  minChars = 2,
  disabled,
  invalid,
  id,
  className,
  emptyText = "Sin coincidencias.",
}: AsyncComboboxProps) {
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState("");
  const debounced = useDebounced(term.trim(), 250);
  const listId = useId();
  const enabled = open && debounced.length >= minChars;
  const { data, isFetching } = useQuery({
    queryKey: [...queryKey, debounced],
    queryFn: () => search(debounced),
    enabled,
    staleTime: 60_000,
  });

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <div className={cn("flex items-center gap-1", className)}>
        <PopoverTrigger asChild>
          <Button
            id={id}
            type="button"
            variant="outline"
            role="combobox"
            aria-expanded={open}
            aria-controls={listId}
            aria-label={value ? `${label}: ${value.label}` : label}
            aria-invalid={invalid}
            disabled={disabled}
            onKeyDown={(event) => {
              if (event.key === "Delete" && value) {
                event.preventDefault();
                onChange(null);
              } else if (event.key.length === 1 && !event.metaKey && !event.ctrlKey && !open) {
                setTerm(event.key);
                setOpen(true);
              }
            }}
            className="h-8 min-w-0 flex-1 justify-between font-normal aria-invalid:border-destructive"
          >
            <span className={cn("truncate", !value && "text-muted-foreground")}>
              {value?.label ?? label}
            </span>
            <ChevronsUpDown className="opacity-50" aria-hidden />
          </Button>
        </PopoverTrigger>
        {value && !disabled ? (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={`Quitar ${label}`}
            onClick={() => onChange(null)}
          >
            <X aria-hidden />
          </Button>
        ) : null}
      </div>
      <PopoverContent className="w-(--radix-popover-trigger-width) min-w-72 p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput
            value={term}
            onValueChange={setTerm}
            placeholder={`Buscar (mín. ${minChars} caracteres)…`}
            aria-label={`Buscar ${label}`}
          />
          <CommandList id={listId}>
            {enabled && !isFetching ? <CommandEmpty>{emptyText}</CommandEmpty> : null}
            {isFetching ? <div className="p-3 text-sm text-muted-foreground">Buscando…</div> : null}
            <CommandGroup>
              {(enabled ? (data ?? []) : []).map((item) => (
                <CommandItem
                  key={item.id}
                  value={item.id}
                  onSelect={() => {
                    onChange(item);
                    setOpen(false);
                    setTerm("");
                  }}
                >
                  <Check
                    className={cn(value?.id === item.id ? "opacity-100" : "opacity-0")}
                    aria-hidden
                  />
                  <div className="min-w-0">
                    <div className="truncate">{item.label}</div>
                    {item.hint ? (
                      <div className="truncate text-xs text-muted-foreground">{item.hint}</div>
                    ) : null}
                  </div>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
