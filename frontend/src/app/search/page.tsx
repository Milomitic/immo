"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useQueryState, parseAsInteger, parseAsString } from "nuqs";
import { useListings } from "@/hooks/useListings";
import { filtersToParams, useListingFilters } from "@/components/search/FilterFields";
import { ListingCard } from "@/components/listings/ListingCard";
import { ListingCardList } from "@/components/listings/ListingCardList";
import { FilterSidebar } from "@/components/search/FilterSidebar";
import { ActiveFilters } from "@/components/search/ActiveFilters";
import { ResultsHeader } from "@/components/search/ResultsHeader";
import { ListingCardSkeleton, ListingCardListSkeleton } from "@/components/ui/Skeleton";
import { Search, ChevronLeft, ChevronRight, Home, GitCompare } from "lucide-react";
import type { ListingSearchParams } from "@/lib/types";

export default function SearchPage() {
  return (
    <Suspense fallback={<div className="flex justify-center py-20"><div className="h-8 w-8 animate-spin rounded-full border-4 border-[var(--primary)] border-t-transparent" /></div>}>
      <SearchContent />
    </Suspense>
  );
}

function SearchContent() {
  const { values } = useListingFilters();
  const [q, setQ] = useQueryState("q", parseAsString);
  const [sort] = useQueryState("sort", parseAsString);
  const [page, setPage] = useQueryState("page", parseAsInteger);
  const [pageSizeParam] = useQueryState("page_size", parseAsInteger);
  const [view] = useQueryState("view", parseAsString);
  // Polygon perimeter — set by the user on /map and carried across to
  // /search via the Header's preserved-params. The chip in ActiveFilters
  // is the user's "remove" affordance so we don't need a setter here.
  const [polygonStr] = useQueryState("polygon", parseAsString);

  const currentView = view || "grid";
  const currentPage = page || 1;
  // Cap to backend's hard limit (100) — page_size is also validated there
  // but we sanitize here so the UI never asks for nonsense.
  const currentPageSize = [20, 50, 100].includes(pageSizeParam ?? 0)
    ? (pageSizeParam as number)
    : 20;

  // Comparison state
  const [compareIds, setCompareIds] = useState<Set<string>>(new Set());
  const handleCompareToggle = (id: string, checked: boolean) => {
    setCompareIds(prev => {
      const next = new Set(prev);
      if (checked && next.size < 3) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const filterParams = filtersToParams(values);

  // Any filter change sends the user back to page 1 — otherwise sitting on
  // page 5 and narrowing the filters shows an empty "Nessun risultato".
  const filterSignature = JSON.stringify([filterParams, q, polygonStr, sort, currentPageSize]);
  const prevSignature = useRef(filterSignature);
  useEffect(() => {
    if (prevSignature.current !== filterSignature) {
      prevSignature.current = filterSignature;
      setPage(null);
    }
  }, [filterSignature, setPage]);

  const params: ListingSearchParams = {
    ...filterParams,
    q: q || undefined,
    polygon: polygonStr || undefined,
    sort: sort || "newest",
    page: currentPage,
    page_size: currentPageSize,
  };

  const { data, isLoading, error } = useListings(params);

  return (
    <div className="mx-auto max-w-[var(--content-max)] px-4 py-4 sm:px-6 lg:px-8">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-1.5 text-xs text-[var(--muted-foreground)] mb-4">
        <Link href="/" className="hover:text-[var(--primary)] transition-colors flex items-center gap-1">
          <Home className="h-3 w-3" /> Home
        </Link>
        <span>/</span>
        <span className="text-[var(--foreground)]">
          {values.listingType === "rent" ? "Affitto" : "Vendita"}
          {values.city ? ` a ${values.city.charAt(0).toUpperCase() + values.city.slice(1)}` : ""}
        </span>
      </nav>

      {/* Search bar */}
      <div className="mb-4">
        <div className="relative max-w-2xl">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--muted-foreground)]" />
          <input
            type="text"
            value={q || ""}
            onChange={(e) => { setQ(e.target.value || null); setPage(null); }}
            placeholder="Cerca per indirizzo, zona, descrizione..."
            className="w-full pl-10 pr-4 py-2.5 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--background)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--primary)] focus:border-transparent transition-shadow"
          />
        </div>
      </div>

      {/* Polygon-active banner — explains why the result count may be
          smaller than the user expects, and gives a one-click escape to
          /map where the perimeter can be edited or redrawn. */}
      {polygonStr && (
        <Link
          href={`/map?${(() => {
            // Carry every current param to /map so the polygon stays
            // visible alongside whatever filters the user has set.
            const sp = new URLSearchParams();
            const all = typeof window !== "undefined" ? window.location.search.slice(1) : "";
            new URLSearchParams(all).forEach((v, k) => {
              if (k !== "page" && k !== "view") sp.set(k, v);
            });
            return sp.toString();
          })()}`}
          className="mb-3 group flex items-center gap-3 rounded-[var(--radius-md)] border border-[var(--primary)]/30 bg-[var(--primary)]/5 px-4 py-2.5 text-sm hover:bg-[var(--primary)]/10 transition-colors"
        >
          <span className="text-base" aria-hidden>📐</span>
          <span className="flex-1">
            <span className="font-semibold text-[var(--primary)]">Area disegnata attiva.</span>{" "}
            <span className="text-[var(--muted-foreground)]">
              I risultati sono limitati al perimetro tracciato sulla mappa.
            </span>
          </span>
          <span className="text-xs font-medium text-[var(--primary)] group-hover:underline">
            Modifica sulla mappa →
          </span>
        </Link>
      )}

      {/* Active filters (chip strip — includes the polygon chip) */}
      <div className="mb-4">
        <ActiveFilters />
      </div>

      <div className="flex gap-6">
        {/* Filters */}
        <FilterSidebar />

        {/* Results */}
        <div className="flex-1 min-w-0">
          {/* Results header */}
          <ResultsHeader
            total={data?.total || 0}
            page={currentPage}
            pageSize={currentPageSize}
            isLoading={isLoading}
          />

          {/* Loading skeletons */}
          {isLoading && (
            <div className={currentView === "grid"
              ? "grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-4 mt-4"
              : "flex flex-col gap-4 mt-4"
            }>
              {Array.from({ length: 6 }).map((_, i) =>
                currentView === "grid"
                  ? <ListingCardSkeleton key={i} />
                  : <ListingCardListSkeleton key={i} />
              )}
            </div>
          )}

          {/* Error */}
          {error && !isLoading && (
            <div className="text-center py-20 text-[var(--destructive)]">
              Errore nel caricamento. Riprova.
            </div>
          )}

          {/* Results */}
          {data && !isLoading && data.items.length > 0 && (
            <>
              {currentView === "grid" ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-4 mt-4">
                  {data.items.map((listing) => (
                    <ListingCard
                      key={listing.id}
                      listing={listing}
                      onCompareToggle={handleCompareToggle}
                      isCompareSelected={compareIds.has(listing.id)}
                    />
                  ))}
                </div>
              ) : (
                <div className="flex flex-col gap-4 mt-4">
                  {data.items.map((listing) => (
                    <ListingCardList
                      key={listing.id}
                      listing={listing}
                      onCompareToggle={handleCompareToggle}
                      isCompareSelected={compareIds.has(listing.id)}
                    />
                  ))}
                </div>
              )}

              {/* Pagination */}
              {data.total_pages > 1 && (
                <div className="flex items-center justify-center gap-4 mt-8 pb-4">
                  <button
                    onClick={() => setPage(Math.max(1, currentPage - 1))}
                    disabled={currentPage <= 1}
                    className="flex items-center gap-1 px-4 py-2 rounded-[var(--radius-md)] border border-[var(--border)] text-sm font-medium disabled:opacity-30 hover:bg-[var(--muted)] transition-colors"
                  >
                    <ChevronLeft className="h-4 w-4" /> Precedente
                  </button>
                  <span className="text-sm text-[var(--muted-foreground)]">
                    Pagina <span className="font-semibold text-[var(--foreground)]">{currentPage}</span> di {data.total_pages}
                  </span>
                  <button
                    onClick={() => setPage(Math.min(data.total_pages, currentPage + 1))}
                    disabled={currentPage >= data.total_pages}
                    className="flex items-center gap-1 px-4 py-2 rounded-[var(--radius-md)] border border-[var(--border)] text-sm font-medium disabled:opacity-30 hover:bg-[var(--muted)] transition-colors"
                  >
                    Successiva <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              )}
            </>
          )}

          {/* Empty state */}
          {data && !isLoading && data.items.length === 0 && (
            <div className="text-center py-20">
              <Search className="h-12 w-12 mx-auto mb-4 text-[var(--muted-foreground)] opacity-40" />
              <h3 className="text-lg font-semibold mb-2">Nessun risultato</h3>
              <p className="text-sm text-[var(--muted-foreground)]">
                Prova a modificare i filtri o ad ampliare la ricerca.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Floating compare button */}
      {compareIds.size >= 2 && (
        <Link
          href={`/compare?ids=${Array.from(compareIds).join(",")}`}
          className="fixed bottom-6 right-6 z-40 flex items-center gap-2 px-5 py-3 rounded-full bg-[var(--primary)] text-[var(--primary-foreground)] font-semibold text-sm shadow-lg hover:opacity-90 transition-opacity"
        >
          <GitCompare className="h-4 w-4" />
          Confronta ({compareIds.size})
        </Link>
      )}
    </div>
  );
}
