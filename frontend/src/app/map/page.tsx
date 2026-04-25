"use client";

import { Suspense, useCallback, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useQueryState, parseAsString } from "nuqs";
import { useMapMarkers } from "@/hooks/useListings";
import { formatArea, formatPrice, roomsLabel } from "@/lib/utils";
import { Building2, MapPin } from "lucide-react";
import type { ListingSearchParams } from "@/lib/types";
import { useListingFilters } from "@/components/search/FilterFields";
import { MapFilters } from "@/components/map/MapFilters";

const MapView = dynamic(() => import("@/components/map/MapView"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full flex items-center justify-center bg-[var(--muted)] text-sm text-[var(--muted-foreground)]">
      Caricamento mappa...
    </div>
  ),
});

// Default view: Bari
const DEFAULT_CENTER: [number, number] = [41.1171, 16.8719];
const DEFAULT_ZOOM = 13;

export default function MapPage() {
  return (
    <Suspense
      fallback={
        <div className="flex justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-[var(--primary)] border-t-transparent" />
        </div>
      }
    >
      <MapPageContent />
    </Suspense>
  );
}

function MapPageContent() {
  const { values, setters } = useListingFilters();
  const [bbox, setBbox] = useQueryState("bbox", parseAsString);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const params: ListingSearchParams & { limit: number } = {
    city: values.city || undefined,
    zone: values.zone || undefined,
    listing_type: values.listingType || undefined,
    property_type: values.propertyType || undefined,
    price_min: values.priceMin || undefined,
    price_max: values.priceMax || undefined,
    area_min: values.areaMin || undefined,
    area_max: values.areaMax || undefined,
    rooms_min: values.roomsMin || undefined,
    bathrooms_min: values.bathroomsMin || undefined,
    floor_min: values.floorMin ?? undefined,
    floor_max: values.floorMax ?? undefined,
    energy_class: values.energyClass || undefined,
    condition: values.condition || undefined,
    has_elevator: values.hasElevator || undefined,
    has_balcony: values.hasBalcony || undefined,
    has_terrace: values.hasTerrace || undefined,
    has_garage: values.hasGarage || undefined,
    has_garden: values.hasGarden || undefined,
    source_portal: values.sourcePortal || undefined,
    bbox: bbox || undefined,
    limit: 1000,
  };

  const { data, isLoading } = useMapMarkers(params);
  const markers = data?.markers ?? [];

  const handleViewportChange = useCallback(
    (newBbox: string) => {
      setBbox(newBbox);
    },
    [setBbox],
  );

  const handleMarkerClick = useCallback((id: string) => {
    setSelectedId(id);
    const el = document.getElementById(`map-list-${id}`);
    el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, []);

  const { listingType } = values;
  const { setListingType } = setters;

  return (
    <div className="h-[calc(100vh-3.5rem)] flex flex-col">
      {/* Filter bar */}
      <div className="border-b border-[var(--border)] bg-[var(--background)] px-4 py-2 shrink-0">
        <div className="flex items-center gap-2 flex-wrap">
          {/* Quick listing-type toggle (most common filter, kept inline) */}
          <div className="flex rounded-[var(--radius-sm)] overflow-hidden border border-[var(--border)]">
            <button
              onClick={() => setListingType(null)}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                !listingType
                  ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                  : "hover:bg-[var(--muted)]"
              }`}
            >
              Tutti
            </button>
            <button
              onClick={() => setListingType("sale")}
              className={`px-3 py-1.5 text-xs font-medium border-l border-[var(--border)] transition-colors ${
                listingType === "sale"
                  ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                  : "hover:bg-[var(--muted)]"
              }`}
            >
              Vendita
            </button>
            <button
              onClick={() => setListingType("rent")}
              className={`px-3 py-1.5 text-xs font-medium border-l border-[var(--border)] transition-colors ${
                listingType === "rent"
                  ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                  : "hover:bg-[var(--muted)]"
              }`}
            >
              Affitto
            </button>
          </div>

          {/* All other filters live in this dropdown */}
          <MapFilters />

          <span className="text-xs text-[var(--muted-foreground)] ml-auto">
            {isLoading
              ? "Caricamento..."
              : `${data?.total ?? 0} annunci${
                  data?.truncated ? ` (primi ${markers.length})` : ""
                }`}
          </span>
        </div>
      </div>

      {/* Split layout */}
      <div className="flex-1 flex overflow-hidden min-h-0">
        {/* Left: scrollable list */}
        <div className="w-96 shrink-0 border-r border-[var(--border)] overflow-y-auto">
          {markers.length === 0 && !isLoading && (
            <div className="p-6 text-center text-sm text-[var(--muted-foreground)]">
              Nessun annuncio in questa area.
              <br />
              Sposta la mappa o allenta i filtri per cercare.
            </div>
          )}
          {markers.map((m) => (
            <Link
              key={m.id}
              id={`map-list-${m.id}`}
              href={`/listing/${m.id}`}
              onMouseEnter={() => setSelectedId(m.id)}
              onMouseLeave={() => setSelectedId(null)}
              className={`flex gap-3 p-3 border-b border-[var(--border)] hover:bg-[var(--muted)] transition-colors ${
                selectedId === m.id ? "bg-[var(--muted)]" : ""
              }`}
            >
              <div className="w-24 h-20 shrink-0 rounded-[var(--radius-sm)] overflow-hidden bg-[var(--muted)]">
                {m.thumbnail ? (
                  <img
                    src={m.thumbnail}
                    alt=""
                    referrerPolicy="no-referrer"
                    loading="lazy"
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-[var(--muted-foreground)]">
                    <Building2 className="h-6 w-6 opacity-40" />
                  </div>
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-bold text-[var(--primary)]">
                  {m.price ? formatPrice(m.price) : "Prezzo su richiesta"}
                </div>
                <div className="text-xs font-medium truncate mt-0.5">
                  {m.rooms ? roomsLabel(m.rooms) + " · " : ""}
                  {m.title}
                </div>
                <div className="text-xs text-[var(--muted-foreground)] truncate flex items-center gap-1 mt-0.5">
                  <MapPin className="h-3 w-3 shrink-0" />
                  {m.zone ? `${m.zone}, ` : ""}
                  <span className="capitalize">{m.city}</span>
                </div>
                {m.area_sqm && (
                  <div className="text-xs text-[var(--muted-foreground)] mt-0.5">
                    {formatArea(m.area_sqm)}
                  </div>
                )}
              </div>
            </Link>
          ))}
        </div>

        {/* Right: map */}
        <div className="flex-1 relative min-w-0">
          <MapView
            markers={markers}
            center={DEFAULT_CENTER}
            zoom={DEFAULT_ZOOM}
            onViewportChange={handleViewportChange}
            selectedId={selectedId}
            onMarkerClick={handleMarkerClick}
          />
        </div>
      </div>
    </div>
  );
}
