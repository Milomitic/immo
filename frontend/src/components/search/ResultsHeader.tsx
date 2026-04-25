"use client";

import { useQueryState, parseAsString } from "nuqs";
import { LayoutGrid, List } from "lucide-react";
import { cn } from "@/lib/utils";

interface ResultsHeaderProps {
  total: number;
  page: number;
  pageSize: number;
  isLoading: boolean;
}

export function ResultsHeader({ total, page, pageSize, isLoading }: ResultsHeaderProps) {
  const [sort, setSort] = useQueryState("sort", parseAsString);
  const [view, setView] = useQueryState("view", parseAsString);
  const currentView = view || "grid";

  const from = total > 0 ? (page - 1) * pageSize + 1 : 0;
  const to = Math.min(page * pageSize, total);

  return (
    <div className="sticky top-0 z-10 bg-[var(--background)] border-b border-[var(--border)] -mx-4 px-4 sm:-mx-0 sm:px-0 sm:border-0 sm:static">
      <div className="flex items-center justify-between py-3">
        <div className="text-sm text-[var(--muted-foreground)]">
          {isLoading ? (
            <span className="animate-pulse">Caricamento...</span>
          ) : total > 0 ? (
            <>
              <span className="font-semibold text-[var(--foreground)]">{from}-{to}</span> di{" "}
              <span className="font-semibold text-[var(--foreground)]">{total.toLocaleString("it-IT")}</span> risultati
            </>
          ) : (
            "Nessun risultato"
          )}
        </div>

        <div className="flex items-center gap-3">
          {/* Sort */}
          <select
            value={sort || "newest"}
            onChange={(e) => setSort(e.target.value === "newest" ? null : e.target.value)}
            className="px-3 py-1.5 rounded-[var(--radius-sm)] border border-[var(--border)] bg-[var(--background)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
          >
            <option value="newest">Piu recenti</option>
            <option value="price_asc">Prezzo crescente</option>
            <option value="price_desc">Prezzo decrescente</option>
            <option value="area_desc">Superficie decrescente</option>
          </select>

          {/* View toggle */}
          <div className="hidden sm:flex items-center border border-[var(--border)] rounded-[var(--radius-sm)] overflow-hidden">
            <button
              onClick={() => setView(null)}
              className={cn(
                "p-1.5 transition-colors",
                currentView === "grid" ? "bg-[var(--primary)] text-[var(--primary-foreground)]" : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
              )}
              title="Vista griglia"
            >
              <LayoutGrid className="h-4 w-4" />
            </button>
            <button
              onClick={() => setView("list")}
              className={cn(
                "p-1.5 transition-colors",
                currentView === "list" ? "bg-[var(--primary)] text-[var(--primary-foreground)]" : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
              )}
              title="Vista lista"
            >
              <List className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
