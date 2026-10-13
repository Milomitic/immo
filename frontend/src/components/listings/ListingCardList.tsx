"use client";

import Link from "next/link";
import { MapPin, Maximize2, BedDouble, Bath, Building2, Camera, Layers } from "lucide-react";
import type { Listing } from "@/lib/types";
import { formatPrice, formatArea, portalLabel, portalColor, publishedAgo, floorLabel, isNewListing, roomsLabel, imageVariant } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import { PriceChangeBadge } from "@/components/listings/PriceChangeBadge";

interface ListingCardListProps {
  listing: Listing;
  onCompareToggle?: (id: string, checked: boolean) => void;
  isCompareSelected?: boolean;
}

export function ListingCardList({ listing, onCompareToggle, isCompareSelected }: ListingCardListProps) {
  const firstImage = listing.images?.[0];
  const photoCount = listing.images?.length || 0;

  return (
    <div className="group rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--background)] overflow-hidden flex transition-shadow duration-200 hover:shadow-[var(--card-hover-shadow)]">
      {/* Image */}
      <Link href={`/listing/${listing.id}`} className="relative w-72 shrink-0 bg-[var(--muted)] overflow-hidden">
        {firstImage ? (
          <img
            src={imageVariant(firstImage, "card")}
            alt={listing.title}
            referrerPolicy="no-referrer"
            loading="lazy"
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-[var(--muted-foreground)]">
            <Building2 className="h-12 w-12 opacity-40" />
          </div>
        )}

        {/* Badges */}
        <div className="absolute top-2.5 left-2.5 flex flex-col gap-1.5">
          <Badge variant="primary" size="sm" className={portalColor(listing.source_portal)}>
            {portalLabel(listing.source_portal)}
          </Badge>
          {isNewListing(listing.first_seen_at) && (
            <Badge variant="warning" size="sm">Nuovo</Badge>
          )}
        </div>

        {photoCount > 1 && (
          <span className="absolute bottom-2.5 right-2.5 flex items-center gap-1 px-2 py-0.5 rounded-full bg-black/60 text-white text-[11px] font-medium">
            <Camera className="h-3 w-3" /> {photoCount}
          </span>
        )}
      </Link>

      {/* Content */}
      <div className="flex-1 p-5 flex flex-col">
        {/* Price row */}
        <div className="flex items-baseline justify-between mb-1">
          <span className="text-xl font-bold text-[var(--primary)] flex items-baseline gap-2">
            {formatPrice(listing.price)}
            {listing.listing_type === "rent" && listing.price ? <span className="text-sm font-normal">/mese</span> : ""}
            <PriceChangeBadge
              price={listing.price}
              pricePrevious={listing.price_previous}
              priceChangedAt={listing.price_changed_at}
            />
            {listing.price_previous != null && listing.price != null && listing.price_previous !== listing.price && (
              <span className="text-xs text-[var(--muted-foreground)] line-through font-normal">
                {formatPrice(listing.price_previous)}
              </span>
            )}
          </span>
          {listing.price_per_sqm && (
            <span className="text-xs text-[var(--muted-foreground)]">
              {formatPrice(listing.price_per_sqm)}/m&sup2;
            </span>
          )}
        </div>

        {/* Title */}
        <h3 className="text-sm font-semibold text-[var(--foreground)] line-clamp-1 mb-1">
          <Link href={`/listing/${listing.id}`} className="hover:text-[var(--primary)] transition-colors">
            {listing.rooms ? roomsLabel(listing.rooms) + " - " : ""}{listing.title}
          </Link>
        </h3>

        {/* Location */}
        <div className="flex items-center gap-1 text-xs text-[var(--muted-foreground)] mb-2">
          <MapPin className="h-3 w-3 shrink-0" />
          <span className="truncate">
            {listing.zone ? `${listing.zone}, ` : ""}{listing.address ? `${listing.address}, ` : ""}<span className="capitalize">{listing.city}</span>
          </span>
        </div>

        {/* Info bar */}
        <div className="flex items-center gap-1 text-xs text-[var(--muted-foreground)] mb-3">
          {listing.rooms && (
            <span className="flex items-center gap-1 pr-2.5 border-r border-[var(--border)]">
              <BedDouble className="h-3.5 w-3.5" /> {listing.rooms} locali
            </span>
          )}
          {listing.area_sqm && (
            <span className="flex items-center gap-1 px-2.5 border-r border-[var(--border)]">
              <Maximize2 className="h-3.5 w-3.5" /> {formatArea(listing.area_sqm)}
            </span>
          )}
          {listing.bathrooms && (
            <span className="flex items-center gap-1 px-2.5 border-r border-[var(--border)]">
              <Bath className="h-3.5 w-3.5" /> {listing.bathrooms} bagni
            </span>
          )}
          {listing.floor && (
            <span className="flex items-center gap-1 pl-2.5">
              <Building2 className="h-3.5 w-3.5" /> {floorLabel(listing.floor)}
            </span>
          )}
        </div>

        {/* Description preview */}
        {listing.description && (
          <p className="text-xs text-[var(--muted-foreground)] line-clamp-2 mb-3 leading-relaxed">
            {listing.description}
          </p>
        )}

        {/* Footer */}
        <div className="mt-auto flex items-center justify-between text-xs text-[var(--muted-foreground)] pt-3 border-t border-[var(--border)]">
          <div className="flex items-center gap-3">
            <span>{publishedAgo(listing.publication_date) ?? "Data non disponibile"}</span>
            {listing.source_count > 1 && (
              <span className="flex items-center gap-1 text-purple-600">
                <Layers className="h-3 w-3" /> {listing.source_count} fonti
              </span>
            )}
          </div>
          {onCompareToggle && (
            <label className="flex items-center gap-1.5 cursor-pointer hover:text-[var(--primary)] transition-colors" onClick={(e) => e.stopPropagation()}>
              <input
                type="checkbox"
                checked={isCompareSelected || false}
                onChange={(e) => onCompareToggle(listing.id, e.target.checked)}
                className="h-3.5 w-3.5 rounded accent-[var(--primary)]"
              />
              Confronta
            </label>
          )}
        </div>
      </div>
    </div>
  );
}
