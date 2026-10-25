import { useEffect, useRef } from "react";

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.isContentEditable ||
    ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) ||
    target.closest("[role=dialog] [cmdk-input]") !== null
  );
}

/**
 * Global shortcut. `combo` is a key, optionally prefixed with "mod+" (Ctrl or ⌘), e.g. "/",
 * "n" or "mod+k". Plain keys are ignored while typing in a field; "mod+" combos always fire.
 */
export function useHotkey(combo: string, handler: (event: KeyboardEvent) => void, enabled = true) {
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => {
    if (!enabled) return;
    const mod = combo.startsWith("mod+");
    const key = mod ? combo.slice(4) : combo;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key.toLowerCase() !== key.toLowerCase()) return;
      const pressedMod = event.metaKey || event.ctrlKey;
      if (mod !== pressedMod || event.altKey) return;
      if (!mod && isTyping(event.target)) return;
      event.preventDefault();
      ref.current(event);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [combo, enabled]);
}
