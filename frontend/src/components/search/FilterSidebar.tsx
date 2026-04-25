"use client";

import { SlidersHorizontal, X } from "lucide-react";
import { useState } from "react";
import { FilterFields, useListingFilters } from "./FilterFields";

export function FilterSidebar() {
  const [isOpen, setIsOpen] = useState(false);
  const { activeCount } = useListingFilters();

  return (
    <>
      {/* Mobile toggle */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="lg:hidden flex items-center gap-2 px-4 py-2.5 rounded-[var(--radius-md)] border border-[var(--border)] text-sm font-medium hover:bg-[var(--muted)] transition-colors"
      >
        <SlidersHorizontal className="h-4 w-4" />
        Filtri
        {activeCount > 0 && (
          <span className="inline-flex items-center justify-center h-5 min-w-5 px-1 rounded-full bg-[var(--primary)] text-[var(--primary-foreground)] text-[10px] font-bold">
            {activeCount}
          </span>
        )}
      </button>

      {/* Mobile overlay */}
      {isOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setIsOpen(false)} />
          <div className="absolute right-0 top-0 h-full w-[min(380px,90vw)] bg-[var(--background)] shadow-2xl overflow-y-auto">
            <div className="sticky top-0 z-10 flex items-center justify-between p-4 bg-[var(--background)] border-b border-[var(--border)]">
              <h2 className="font-bold">Filtri</h2>
              <button onClick={() => setIsOpen(false)} className="p-1 rounded hover:bg-[var(--muted)]">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="p-4">
              <FilterFields />
            </div>
            <div className="sticky bottom-0 p-4 bg-[var(--background)] border-t border-[var(--border)]">
              <button
                onClick={() => setIsOpen(false)}
                className="w-full py-2.5 rounded-[var(--radius-md)] bg-[var(--primary)] text-[var(--primary-foreground)] text-sm font-semibold hover:opacity-90 transition-opacity"
              >
                Mostra risultati
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Desktop sidebar — sticks below the header, scrolls its own overflow */}
      <aside className="hidden lg:block w-80 shrink-0 self-start sticky top-[4.5rem]">
        <div
          className="rounded-[var(--radius-lg)] border border-[var(--border)] p-5 max-h-[calc(100vh-5.5rem)] overflow-y-auto overscroll-contain"
          style={{ boxShadow: "var(--card-shadow)" }}
        >
          <FilterFields />
        </div>
      </aside>
    </>
  );
}
