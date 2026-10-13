"use client";

import Link from "next/link";
import { Heart, Search } from "lucide-react";
import { useFavorites } from "@/hooks/useFavorites";
import { ListingCard } from "@/components/listings/ListingCard";
import { ListingCardSkeleton } from "@/components/ui/Skeleton";

const GRID = "grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-4 mt-4";

export default function FavoritesPage() {
  const { data, isLoading, isError } = useFavorites();
  const favorites = data ?? [];
  const gone = favorites.filter((f) => !f.listing.is_active).length;

  return (
    <div className="mx-auto max-w-[var(--content-max)] px-4 py-6 sm:px-6 lg:px-8">
      <div className="flex items-baseline justify-between gap-4">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Heart className="h-6 w-6 fill-red-500 text-red-500" />
          Preferiti
          {favorites.length > 0 && (
            <span className="text-base font-normal text-[var(--muted-foreground)]">({favorites.length})</span>
          )}
        </h1>
        {gone > 0 && (
          <span className="text-sm text-[var(--muted-foreground)]">
            {gone === 1 ? "1 annuncio non è più sul mercato" : `${gone} annunci non sono più sul mercato`}
          </span>
        )}
      </div>

      {isLoading && (
        <div className={GRID}>
          {Array.from({ length: 4 }, (_, i) => <ListingCardSkeleton key={i} />)}
        </div>
      )}

      {isError && (
        <p role="alert" className="mt-6 text-sm text-[var(--destructive)]">
          Impossibile caricare i preferiti. Il backend è raggiungibile?
        </p>
      )}

      {!isLoading && !isError && favorites.length === 0 && (
        <div className="mt-16 flex flex-col items-center text-center gap-3 text-[var(--muted-foreground)]">
          <Heart className="h-12 w-12 opacity-30" />
          <p className="text-base font-medium text-[var(--foreground)]">Nessun preferito</p>
          <p className="text-sm max-w-sm">
            Tocca il cuore su un annuncio per salvarlo qui: ne seguirai prezzo e disponibilità.
          </p>
          <Link
            href="/search"
            className="mt-2 inline-flex items-center gap-1.5 px-4 py-2 rounded-full bg-[var(--primary)] text-[var(--primary-foreground)] text-sm font-medium hover:opacity-90 transition-opacity"
          >
            <Search className="h-4 w-4" /> Cerca annunci
          </Link>
        </div>
      )}

      {favorites.length > 0 && (
        <div className={GRID}>
          {favorites.map(({ listing }) => (
            <div key={listing.id} className="relative">
              <div className={listing.is_active ? undefined : "opacity-60 grayscale"}>
                <ListingCard listing={listing} />
              </div>
              {!listing.is_active && (
                // Centred on the photo, which has the card's 4/3 ratio.
                <div className="pointer-events-none absolute inset-x-0 top-0 aspect-[4/3] flex items-center justify-center">
                  <span className="px-3 py-1 rounded-full bg-black/75 text-white text-xs font-semibold">
                    Non più disponibile
                  </span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
