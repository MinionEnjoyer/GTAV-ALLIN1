import { useEffect, useRef, type ReactNode } from "react";

export const descriptions: Record<string, string> = {
  setup: "Choose a GTA V installation, verify its prerequisites, and review any repair before it runs.",
  gameplay: "Adjust Story Mode traffic, vehicles, and gameplay preferences. Changes remain a local draft until you review them.",
  input: "Set keyboard, controller, and accessibility preferences for the selected installation.",
  content: "Manage included content, integrations, and traffic population settings from one workspace.",
  mods: "Inspect packages before installation, manage installed packages, and find included content and SDK examples.",
  characters: "Manage character progress, loadouts, outfits, and saved garage vehicles with reviewed writes.",
  sdk: "Manage the ALLIN1 SDK and optional assistant tools, with clear review steps for supported changes.",
  activity: "Review this session’s operations, export diagnostics, and check Launcher release information.",
  help: "Find setup guidance, safe workflows, and practical automation examples.",
};
const paths: Record<string, string> = {
  setup: "M3 10 12 3l9 7M5 9v12h5v-7h4v7h5V9",
  gameplay: "M7 7h10l4 10-2 3-5-4h-4l-5 4-2-3 4-10ZM7 11v4m-2-2h4m7-1h.01m2 2h.01",
  content: "m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5",
  input: "M3 5h18v14H3V5Zm3 4h1m3 0h1m3 0h1m3 0h1M6 12h1m3 0h1m3 0h1m3 0h1M7 16h10",
  mods: "m3 7 9-4 9 4v10l-9 4-9-4V7Zm0 0 9 4 9-4m-9 4v10M8 5l9 4",
  characters: "M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 21v-3a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v3",
  sdk: "m8 6-6 6 6 6m8-12 6 6-6 6m-3-15-2 18",
  activity: "M3 12h4l3-8 4 16 3-8h4",
  help: "M9 8a3 3 0 1 1 5 2c-2 1-2 2-2 4m0 3h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",
};
export function WorkspaceIcon({ name }: { name: string }) {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d={paths[name] ?? paths.help} /></svg>;
}
export function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return <div className="empty-state"><strong>{title}</strong><p>{children}</p></div>;
}
export function ReviewDialog({ children, busy, cancel }: { children: ReactNode; busy: boolean; cancel: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const dialog = ref.current;
    if (dialog?.showModal) dialog.showModal();
    else dialog?.setAttribute("open", "");
    return () => { dialog?.close?.(); previous?.focus(); };
  }, []);
  return <dialog className="review-dialog" ref={ref} aria-label="Confirm Launcher changes"
    onCancel={(event) => { event.preventDefault(); if (!busy) cancel(); }}>{children}</dialog>;
}
