"use client";

import { useEffect, useRef, useState } from "react";
import { SlidersHorizontal, X } from "lucide-react";
import { FilterFields, useListingFilters } from "@/components/search/FilterFields";

/**
 * "Filtri" button + dropdown popover for the map view.
 *
 * The popover floats below the trigger and dismisses on click-outside or Esc
 * — no full-screen backdrop, since the user wants to keep the map visible
 * while comparing filter selections.
 */
export function MapFilters() {
  const [isOpen, setIsOpen] = useState(false);
  const { activeCount, clearAll } = useListingFilters();
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Click-outside + Esc handler. Attached only while the popover is open
  // so we don't pay the cost of a global listener on every render.
  useEffect(() => {
    if (!isOpen) return;
    const onClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [isOpen]);

  return (
    <div className="relative" ref={containerRef}>
      <button
        onClick={() => setIsOpen((v) => !v)}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-sm)] border text-xs font-medium transition-colors ${
          isOpen || activeCount > 0
            ? "bg-[var(--primary)] text-[var(--primary-foreground)] border-[var(--primary)]"
            : "border-[var(--border)] hover:bg-[var(--muted)]"
        }`}
      >
        <SlidersHorizontal className="h-3.5 w-3.5" />
        Filtri
        {activeCount > 0 && (
          <span
            className={`inline-flex items-center justify-center h-4 min-w-4 px-1 rounded-full text-[10px] font-bold ${
              isOpen
                ? "bg-[var(--primary-foreground)] text-[var(--primary)]"
                : "bg-[var(--primary)] text-[var(--primary-foreground)]"
            }`}
          >
            {activeCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div
          className="absolute left-0 top-full mt-2 z-[1000] w-[360px] max-h-[70vh] overflow-y-auto overscroll-contain rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--background)] shadow-xl"
          style={{ boxShadow: "var(--card-shadow, 0 10px 30px rgba(0,0,0,0.18))" }}
        >
          <div className="sticky top-0 z-10 flex items-center justify-between px-4 py-2.5 bg-[var(--background)] border-b border-[var(--border)]">
            <h3 className="text-sm font-bold">Filtri</h3>
            <div className="flex items-center gap-2">
              {activeCount > 0 && (
                <button
                  onClick={clearAll}
                  className="text-xs font-medium text-[var(--primary)] hover:underline"
                >
                  Resetta
                </button>
              )}
              <button
                onClick={() => setIsOpen(false)}
                className="p-1 rounded hover:bg-[var(--muted)]"
                aria-label="Chiudi filtri"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
          <div className="p-4">
            <FilterFields showHeader={false} />
          </div>
        </div>
      )}
    </div>
  );
}
