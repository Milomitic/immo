"use client";

import Link from "next/link";
import { MapPin, Building2, Camera, Layers } from "lucide-react";
import type { Listing } from "@/lib/types";
import { formatPrice, portalLabel, portalColor, isNewListing, roomsLabel, imageVariant } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import { AuctionBadge } from "@/components/listings/AuctionBadge";
import { FavoriteButton } from "@/components/listings/FavoriteButton";
import { AmenityIcons, KeyFacts } from "@/components/listings/ListingFeatures";
import { PriceChangeBadge } from "@/components/listings/PriceChangeBadge";
import { PublishedAt } from "@/components/listings/PublishedAt";

interface ListingCardProps {
  listing: Listing;
  onCompareToggle?: (id: string, checked: boolean) => void;
  isCompareSelected?: boolean;
}

export function ListingCard({ listing, onCompareToggle, isCompareSelected }: ListingCardProps) {
  const firstImage = listing.images?.[0];
  const photoCount = listing.images?.length || 0;

  return (
    <div className="group rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--background)] overflow-hidden transition-shadow duration-200 hover:shadow-[var(--card-hover-shadow)]">
      {/* Image. The heart sits beside the link, not inside it: a button
          nested in an <a> is invalid and confuses screen readers. */}
      <div className="relative">
        <Link href={`/listing/${listing.id}`}>
          <div className="relative aspect-[4/3] bg-[var(--muted)] overflow-hidden">
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

            {/* Top-left badges */}
            <div className="absolute top-2.5 left-2.5 flex flex-col gap-1.5">
              <Badge variant="primary" size="sm" className={portalColor(listing.source_portal)}>
                {portalLabel(listing.source_portal)}
              </Badge>
              {listing.is_auction && <AuctionBadge />}
              {isNewListing(listing.first_seen_at) && (
                <Badge variant="warning" size="sm">Nuovo</Badge>
              )}
              {listing.source_count > 1 && (
                <Badge variant="default" size="sm" className="bg-purple-600 text-white">
                  <Layers className="h-3 w-3" /> {listing.source_count} fonti
                </Badge>
              )}
            </div>

            {/* Bottom-right: photo count */}
            {photoCount > 1 && (
              <span className="absolute bottom-2.5 right-2.5 flex items-center gap-1 px-2 py-0.5 rounded-full bg-black/60 text-white text-[11px] font-medium">
                <Camera className="h-3 w-3" /> {photoCount}
              </span>
            )}

            {/* Bottom-left: listing type */}
            <span className="absolute bottom-2.5 left-2.5 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-black/60 text-white">
              {listing.listing_type === "rent" ? "Affitto" : "Vendita"}
            </span>
          </div>
        </Link>
        <FavoriteButton listingId={listing.id} className="absolute top-2.5 right-2.5" />
      </div>

      {/* Content */}
      <div className="p-4">
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
          </span>
          {listing.price_per_sqm && (
            <span className="text-xs text-[var(--muted-foreground)]">
              {formatPrice(listing.price_per_sqm)}/m&sup2;
            </span>
          )}
        </div>
        {/* Previous price under the new price when changed */}
        {listing.price_previous != null && listing.price != null && listing.price_previous !== listing.price && (
          <div className="text-xs text-[var(--muted-foreground)] line-through -mt-1 mb-1">
            {formatPrice(listing.price_previous)}
          </div>
        )}

        {/* Title */}
        <p className="text-sm font-medium text-[var(--foreground)] line-clamp-1 mb-1">
          {listing.rooms ? roomsLabel(listing.rooms) + " - " : ""}{listing.title}
        </p>

        {/* Location */}
        <div className="flex items-center gap-1 text-xs text-[var(--muted-foreground)] mb-3">
          <MapPin className="h-3 w-3 shrink-0" />
          <span className="truncate">
            {listing.zone ? `${listing.zone}, ` : ""}{listing.address ? `${listing.address}, ` : ""}<span className="capitalize">{listing.city}</span>
          </span>
        </div>

        {/* Info bar: key facts, amenities on the right (wrapping below
            when the card is narrow). */}
        <div className="flex flex-wrap items-center gap-y-1.5 text-xs text-[var(--muted-foreground)] py-2.5 border-t border-[var(--border)]">
          <KeyFacts listing={listing} />
          <AmenityIcons listing={listing} className="ml-auto pl-2.5" />
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between mt-2.5 text-xs text-[var(--muted-foreground)]">
          <PublishedAt date={listing.publication_date} fallback="Data non disponibile" />
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
