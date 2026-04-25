"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useQueryState, parseAsInteger, parseAsString, parseAsBoolean } from "nuqs";
import { useListings } from "@/hooks/useListings";
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
  const [q, setQ] = useQueryState("q", parseAsString);
  const [city] = useQueryState("city", parseAsString);
  const [zone] = useQueryState("zone", parseAsString);
  const [listingType] = useQueryState("listing_type", parseAsString);
  const [propertyType] = useQueryState("property_type", parseAsString);
  const [priceMin] = useQueryState("price_min", parseAsInteger);
  const [priceMax] = useQueryState("price_max", parseAsInteger);
  const [areaMin] = useQueryState("area_min", parseAsInteger);
  const [areaMax] = useQueryState("area_max", parseAsInteger);
  const [roomsMin] = useQueryState("rooms_min", parseAsInteger);
  const [bathroomsMin] = useQueryState("bathrooms_min", parseAsInteger);
  const [floorMin] = useQueryState("floor_min", parseAsInteger);
  const [floorMax] = useQueryState("floor_max", parseAsInteger);
  const [energyClass] = useQueryState("energy_class", parseAsString);
  const [condition] = useQueryState("condition", parseAsString);
  const [hasElevator] = useQueryState("has_elevator", parseAsBoolean);
  const [hasBalcony] = useQueryState("has_balcony", parseAsBoolean);
  const [hasTerrace] = useQueryState("has_terrace", parseAsBoolean);
  const [hasGarage] = useQueryState("has_garage", parseAsBoolean);
  const [hasGarden] = useQueryState("has_garden", parseAsBoolean);
  const [sourcePortal] = useQueryState("source_portal", parseAsString);
  const [sort] = useQueryState("sort", parseAsString);
  const [page, setPage] = useQueryState("page", parseAsInteger);
  const [view] = useQueryState("view", parseAsString);

  const currentView = view || "grid";
  const currentPage = page || 1;

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

  const params: ListingSearchParams = {
    q: q || undefined,
    city: city || undefined,
    zone: zone || undefined,
    listing_type: listingType || undefined,
    property_type: propertyType || undefined,
    price_min: priceMin || undefined,
    price_max: priceMax || undefined,
    area_min: areaMin || undefined,
    area_max: areaMax || undefined,
    rooms_min: roomsMin || undefined,
    bathrooms_min: bathroomsMin || undefined,
    floor_min: floorMin ?? undefined,
    floor_max: floorMax ?? undefined,
    energy_class: energyClass || undefined,
    has_elevator: hasElevator || undefined,
    has_balcony: hasBalcony || undefined,
    has_terrace: hasTerrace || undefined,
    has_garage: hasGarage || undefined,
    has_garden: hasGarden || undefined,
    source_portal: sourcePortal || undefined,
    sort: sort || "newest",
    page: currentPage,
    page_size: 20,
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
          {listingType === "rent" ? "Affitto" : "Vendita"}
          {city ? ` a ${city.charAt(0).toUpperCase() + city.slice(1)}` : ""}
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

      {/* Active filters */}
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
            pageSize={20}
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
