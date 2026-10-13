"use client";

import { useEffect } from "react";
import { ChevronDown, ChevronUp, SlidersHorizontal } from "lucide-react";
import { FilterFields, useListingFilters } from "@/components/search/FilterFields";
import { cn } from "@/lib/utils";

const PANEL_ID = "map-filters-panel";

/** "Filtri" toggle in the map's top bar. */
export function MapFiltersButton({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const { activeCount } = useListingFilters();
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      aria-controls={PANEL_ID}
      className={cn(
        "flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-sm)] border text-xs font-medium transition-colors",
        open || activeCount > 0
          ? "bg-[var(--primary)] text-[var(--primary-foreground)] border-[var(--primary)]"
          : "border-[var(--border)] hover:bg-[var(--muted)]",
      )}
    >
      <SlidersHorizontal className="h-3.5 w-3.5" />
      Filtri
      {activeCount > 0 && (
        <span
          className={cn(
            "inline-flex items-center justify-center h-4 min-w-4 px-1 rounded-full text-[10px] font-bold",
            "bg-[var(--primary-foreground)] text-[var(--primary)]",
          )}
        >
          {activeCount}
        </span>
      )}
      <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} />
    </button>
  );
}

/**
 * The filters as a sub-bar under the top bar. It pushes the list and the
 * map down rather than floating over them, sections sit side by side, and
 * the map stays usable while it's open (it caps its own height).
 */
export function MapFiltersPanel({ onClose }: { onClose: () => void }) {
  const { activeCount, clearAll } = useListingFilters();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div id={PANEL_ID} className="border-t border-[var(--border)] bg-[var(--background)] shrink-0">
      <div className="max-h-[42vh] overflow-y-auto overscroll-contain px-4 py-3">
        <FilterFields showHeader={false} layout="grid" />
      </div>
      <div className="flex items-center justify-between gap-3 px-4 py-1.5 border-t border-[var(--border)] bg-[var(--muted)]">
        <span className="text-xs text-[var(--muted-foreground)]">
          {activeCount > 0 ? `${activeCount} filtri attivi` : "Nessun filtro attivo"}
        </span>
        <div className="flex items-center gap-3">
          {activeCount > 0 && (
            <button type="button" onClick={clearAll} className="text-xs font-medium text-[var(--primary)] hover:underline">
              Resetta
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            className="flex items-center gap-1 text-xs font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
          >
            <ChevronUp className="h-3.5 w-3.5" /> Chiudi filtri
          </button>
        </div>
      </div>
    </div>
  );
}
