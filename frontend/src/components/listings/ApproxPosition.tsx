import { LocateFixed } from "lucide-react";
import type { GeoPrecision } from "@/lib/types";
import { cn } from "@/lib/utils";

const WHERE: Record<GeoPrecision, string> = {
  address: "stimata dall'indirizzo",
  street: "centro della via",
};

/** The portal gave no position: say how ours was estimated. */
export function approxPositionText(precision: GeoPrecision): string {
  return `Posizione approssimativa: ${WHERE[precision] ?? "stimata"}`;
}

export function ApproxPosition({ precision, className }: { precision: GeoPrecision | null; className?: string }) {
  if (!precision) return null;
  return (
    <p className={cn("flex items-center gap-1 text-[11px] text-[var(--muted-foreground)]", className)}>
      <LocateFixed className="h-3 w-3 shrink-0" aria-hidden />
      {approxPositionText(precision)}
    </p>
  );
}
