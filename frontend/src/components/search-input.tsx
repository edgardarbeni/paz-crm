import { Search } from "lucide-react";
import { useRef } from "react";
import { Kbd } from "@/components/page-header";
import { Input } from "@/components/ui/input";
import { useHotkey } from "@/hooks/use-hotkey";

/** List search box; "/" focuses it from anywhere on the page. */
export function SearchInput({
  value,
  onChange,
  label,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  label: string;
  placeholder?: string;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useHotkey("/", () => ref.current?.focus());
  return (
    <div className="relative w-full max-w-sm">
      <Search
        className="pointer-events-none absolute top-2 left-2.5 size-4 text-muted-foreground"
        aria-hidden
      />
      <Input
        ref={ref}
        type="search"
        aria-label={label}
        placeholder={placeholder ?? label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="pr-10 pl-8"
      />
      <span className="pointer-events-none absolute top-1.5 right-2">
        <Kbd>/</Kbd>
      </span>
    </div>
  );
}
