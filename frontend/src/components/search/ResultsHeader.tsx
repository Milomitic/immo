"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQueryState, parseAsInteger, parseAsString } from "nuqs";
import { LayoutGrid, List, Map as MapIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { SaveSearchButton } from "./SaveSearchButton";

interface ResultsHeaderProps {
  total: number;
  page: number;
  pageSize: number;
  isLoading: boolean;
}

// Order matters in the dropdown: most-used first.
const SORT_OPTIONS: { value: string; label: string }[] = [
  { value: "newest", label: "Più recenti" },
  { value: "price_asc", label: "Prezzo: crescente" },
  { value: "price_desc", label: "Prezzo: decrescente" },
  { value: "price_sqm_asc", label: "€/m² crescente" },
  { value: "price_sqm_desc", label: "€/m² decrescente" },
  { value: "area_desc", label: "Superficie: maggiore" },
  { value: "area_asc", label: "Superficie: minore" },
];

const PAGE_SIZE_OPTIONS = [20, 50, 100];

export function ResultsHeader({ total, page, pageSize, isLoading }: ResultsHeaderProps) {
  const [sort, setSort] = useQueryState("sort", parseAsString);
  const [view, setView] = useQueryState("view", parseAsString);
  const [pageSizeParam, setPageSizeParam] = useQueryState("page_size", parseAsInteger);
  const [, setPage] = useQueryState("page", parseAsInteger);
  const currentView = view || "grid";

  // Build a /map link that carries every current filter param verbatim
  // so toggling between list and map keeps results identical.
  const searchParams = useSearchParams();
  const mapHref = `/map${searchParams.size > 0 ? `?${searchParams.toString()}` : ""}`;

  const from = total > 0 ? (page - 1) * pageSize + 1 : 0;
  const to = Math.min(page * pageSize, total);

  return (
    <div className="sticky top-0 z-10 bg-[var(--background)] border-b border-[var(--border)] -mx-4 px-4 sm:-mx-0 sm:px-0 sm:border-0 sm:static">
      <div className="flex items-center justify-between py-3 gap-3 flex-wrap">
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

        <div className="flex items-center gap-2 flex-wrap">
          <SaveSearchButton />

          {/* Sort */}
          <select
            value={sort || "newest"}
            onChange={(e) => setSort(e.target.value === "newest" ? null : e.target.value)}
            className="px-3 py-1.5 rounded-[var(--radius-sm)] border border-[var(--border)] bg-[var(--background)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
            title="Ordina"
          >
            {SORT_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>

          {/* Page size — UI-only label "Per pagina"; param page_size in URL */}
          <select
            value={pageSizeParam ?? 20}
            onChange={(e) => {
              const n = parseInt(e.target.value);
              setPageSizeParam(n === 20 ? null : n);
              setPage(null); // jump back to page 1 when size changes
            }}
            className="px-3 py-1.5 rounded-[var(--radius-sm)] border border-[var(--border)] bg-[var(--background)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
            title="Annunci per pagina"
          >
            {PAGE_SIZE_OPTIONS.map(n => (
              <option key={n} value={n}>{n}/pag</option>
            ))}
          </select>

          {/* "View on map" — propagates every current filter to /map so
              toggling list↔map gives the exact same result set. */}
          <Link
            href={mapHref}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-sm)] bg-[var(--primary)] text-[var(--primary-foreground)] text-sm font-semibold hover:opacity-90 transition-opacity"
            title="Vedi gli stessi annunci sulla mappa"
          >
            <MapIcon className="h-4 w-4" />
            <span className="hidden sm:inline">Mappa</span>
          </Link>

          {/* Grid / list toggle (within the search page) */}
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
