import { Gavel } from "lucide-react";
import { cn } from "@/lib/utils";

/** Marks judicial / online auctions: their price is a starting bid, not an
 *  asking price, so they must never pass for normal listings. */
export function AuctionBadge({ size = "sm", className }: { size?: "sm" | "md"; className?: string }) {
  return (
    <span
      title="Vendita all'asta: il prezzo è la base d'asta, non il prezzo richiesto"
      className={cn(
        "inline-flex items-center gap-1 rounded-full font-bold uppercase tracking-wide shrink-0",
        "bg-[var(--attention-bg)] text-[var(--attention)] border border-[var(--attention)]/40",
        size === "sm" ? "text-[10px] px-1.5 py-0.5" : "text-xs px-2 py-0.5",
        className,
      )}
    >
      <Gavel className={size === "sm" ? "h-3 w-3" : "h-3.5 w-3.5"} />
      Asta
    </span>
  );
}
