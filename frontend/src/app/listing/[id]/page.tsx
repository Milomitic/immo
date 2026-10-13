"use client";

import { use, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  MapPin, Layers, ExternalLink, ChevronLeft, ChevronRight,
  Home, Expand, Map as MapIcon, Clock,
} from "lucide-react";
import { useListingDetail, useSimilarListings } from "@/hooks/useListings";
import { formatPrice, formatArea, portalLabel, portalColor, propertyTypeLabel, listingTypeLabel, floorLabel, energyClassColor, conditionLabel, seenAgo, imageVariant } from "@/lib/utils";
import { ListingCard } from "@/components/listings/ListingCard";
import { FavoriteButton } from "@/components/listings/FavoriteButton";
import { PriceChangeBadge } from "@/components/listings/PriceChangeBadge";
import { PublishedAt } from "@/components/listings/PublishedAt";
import { PriceHistory } from "@/components/listings/PriceHistory";
import { Badge } from "@/components/ui/Badge";
import { AuctionBadge } from "@/components/listings/AuctionBadge";
import { FACT_ICONS, presentAmenities } from "@/components/listings/featureIcons";
import { Skeleton } from "@/components/ui/Skeleton";
import { ImageLightbox } from "@/components/ui/ImageLightbox";

export default function ListingDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: listing, isLoading } = useListingDetail(id);
  const { data: similar } = useSimilarListings(id);
  const [currentImage, setCurrentImage] = useState(0);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [lightboxIndex, setLightboxIndex] = useState(0);
  const [lightboxSource, setLightboxSource] = useState<"photos" | "plans">("photos");
  const [showStickyPrice, setShowStickyPrice] = useState(false);
  const priceRef = useRef<HTMLDivElement>(null);

  const openLightbox = (i: number, source: "photos" | "plans" = "photos") => {
    setLightboxIndex(i);
    setLightboxSource(source);
    setLightboxOpen(true);
  };

  // Sticky price bar on scroll
  useEffect(() => {
    if (!priceRef.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => setShowStickyPrice(!entry.isIntersecting),
      { threshold: 0 }
    );
    observer.observe(priceRef.current);
    return () => observer.disconnect();
  }, [listing]);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:px-8">
        <Skeleton className="h-4 w-40 mb-4" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-4">
            <Skeleton className="aspect-[16/10] rounded-[var(--radius-lg)]" />
            <Skeleton className="h-8 w-2/3" />
            <Skeleton className="h-6 w-1/3" />
          </div>
          <div className="space-y-4">
            <Skeleton className="h-48 rounded-[var(--radius-lg)]" />
            <Skeleton className="h-32 rounded-[var(--radius-lg)]" />
          </div>
        </div>
      </div>
    );
  }

  if (!listing) {
    return (
      <div className="text-center py-20">
        <h2 className="text-lg font-semibold">Annuncio non trovato</h2>
        <Link href="/search" className="text-[var(--primary)] text-sm mt-2 inline-block">Torna alla ricerca</Link>
      </div>
    );
  }

  const photos = listing.images || [];
  const floorPlans = listing.floor_plans || [];
  // Planimetrie davanti, poi le foto. Single ordered array used for the
  // main carousel + thumbnails; we still keep `floorPlans` separate for
  // the "Planimetria" CTA that opens the lightbox filtered to plans.
  const images = [...floorPlans, ...photos];
  const isFloorPlanIndex = (i: number) => i < floorPlans.length;
  const lightboxImages = (lightboxSource === "plans" ? floorPlans : images).map((u) => imageVariant(u, "full"));

  return (
    <>
      {/* Sticky price bar */}
      {showStickyPrice && (
        <div className="fixed top-0 left-0 right-0 z-50 bg-[var(--background)] border-b border-[var(--border)] shadow-sm">
          <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 py-2.5 flex items-center justify-between">
            <div className="flex items-center gap-3 min-w-0">
              <span className="text-lg font-bold text-[var(--primary)]">
                {formatPrice(listing.price)}{listing.listing_type === "rent" ? "/mese" : ""}
              </span>
              <span className="text-sm text-[var(--muted-foreground)] truncate hidden sm:inline">{listing.title}</span>
            </div>
            <a
              href={listing.listing_url}
              target="_blank"
              rel="noopener noreferrer"
              className="shrink-0 px-4 py-1.5 rounded-[var(--radius-md)] bg-[var(--primary)] text-[var(--primary-foreground)] text-sm font-medium hover:opacity-90 transition-opacity"
            >
              Vedi su {portalLabel(listing.source_portal)}
            </a>
          </div>
        </div>
      )}

      <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:px-8">
        {/* Breadcrumb */}
        <nav className="flex items-center gap-1.5 text-xs text-[var(--muted-foreground)] mb-4">
          <Link href="/" className="hover:text-[var(--primary)] transition-colors flex items-center gap-1"><Home className="h-3 w-3" /> Home</Link>
          <span>/</span>
          <Link href="/search" className="hover:text-[var(--primary)] transition-colors">Ricerca</Link>
          <span>/</span>
          <span className="text-[var(--foreground)] truncate max-w-[200px]">{listing.title}</span>
        </nav>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main content */}
          <div className="lg:col-span-2 space-y-6">
            {/* Image Gallery */}
            {images.length > 0 && (
              <div className="space-y-2">
                <div className="relative rounded-[var(--radius-lg)] overflow-hidden bg-[var(--muted)] group/gallery">
                  <button
                    type="button"
                    onClick={() => openLightbox(currentImage, "photos")}
                    className="block w-full cursor-zoom-in"
                    aria-label="Ingrandisci foto"
                  >
                    <div className="aspect-[16/10]">
                      <img src={imageVariant(images[currentImage], "full")} alt={`Foto ${currentImage + 1}`} referrerPolicy="no-referrer" className="w-full h-full object-cover" />
                    </div>
                  </button>
                  {/* Expand hint */}
                  <span className="pointer-events-none absolute top-3 right-3 flex items-center gap-1 px-2.5 py-1 rounded-full bg-black/55 text-white text-xs opacity-0 group-hover/gallery:opacity-100 transition-opacity">
                    <Expand className="h-3.5 w-3.5" /> Ingrandisci
                  </span>
                  {/* Badge "Planimetria" when the current image IS a floor plan */}
                  {isFloorPlanIndex(currentImage) && (
                    <span className="absolute top-3 left-3 flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[var(--primary)] text-[var(--primary-foreground)] text-xs font-semibold shadow-md">
                      <MapIcon className="h-3.5 w-3.5" /> Planimetria
                      {floorPlans.length > 1 ? ` ${currentImage + 1}/${floorPlans.length}` : ""}
                    </span>
                  )}
                  {/* CTA "Vedi planimetrie" when on a photo and floor plans exist */}
                  {!isFloorPlanIndex(currentImage) && floorPlans.length > 0 && (
                    <button
                      type="button"
                      onClick={() => { setCurrentImage(0); }}
                      className="absolute top-3 left-3 flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[var(--primary)] text-[var(--primary-foreground)] text-xs font-semibold shadow-md hover:opacity-90 transition-opacity"
                      aria-label="Vai alla planimetria"
                    >
                      <MapIcon className="h-3.5 w-3.5" /> Planimetria
                      {floorPlans.length > 1 ? ` (${floorPlans.length})` : ""}
                    </button>
                  )}
                  {images.length > 1 && (
                    <>
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); setCurrentImage((currentImage - 1 + images.length) % images.length); }}
                        className="absolute left-3 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-black/50 text-white flex items-center justify-center hover:bg-black/70 transition-colors"
                        aria-label="Foto precedente"
                      >
                        <ChevronLeft className="h-5 w-5" />
                      </button>
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); setCurrentImage((currentImage + 1) % images.length); }}
                        className="absolute right-3 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-black/50 text-white flex items-center justify-center hover:bg-black/70 transition-colors"
                        aria-label="Foto successiva"
                      >
                        <ChevronRight className="h-5 w-5" />
                      </button>
                      <span className="absolute bottom-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full bg-black/50 text-white text-xs">
                        {currentImage + 1} / {images.length}
                      </span>
                    </>
                  )}
                </div>
                {/* Thumbnail strip */}
                {images.length > 1 && (
                  <div className="flex gap-1.5 overflow-x-auto pb-1">
                    {images.slice(0, 12).map((img, i) => (
                      <button
                        key={i}
                        onClick={() => { setCurrentImage(i); openLightbox(i, "photos"); }}
                        className={`relative shrink-0 w-16 h-12 rounded-[var(--radius-sm)] overflow-hidden border-2 transition-colors ${i === currentImage ? "border-[var(--primary)]" : "border-transparent opacity-60 hover:opacity-100"}`}
                      >
                        <img src={imageVariant(img, "card")} alt="" referrerPolicy="no-referrer" className="w-full h-full object-cover" />
                        {/* Marker on planimetry thumbnails so users know
                            what they're clicking before the carousel
                            advances. */}
                        {isFloorPlanIndex(i) && (
                          <span className="absolute bottom-0 left-0 right-0 bg-[var(--primary)]/90 text-[var(--primary-foreground)] text-[9px] font-bold leading-none py-0.5 text-center uppercase tracking-wide">
                            Plan
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Title & Price */}
            <div ref={priceRef}>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-start gap-2">
                    <h1 className="text-xl sm:text-2xl font-bold">{listing.title}</h1>
                    <FavoriteButton listingId={listing.id} size="md" className="shrink-0 border border-[var(--border)]" />
                  </div>
                  {(listing.address || listing.zone) && (
                    <div className="flex items-center gap-1.5 mt-1.5 text-[var(--muted-foreground)] text-sm">
                      <MapPin className="h-4 w-4 shrink-0" />
                      {listing.zone ? `${listing.zone}, ` : ""}{listing.address ? `${listing.address}, ` : ""}<span className="capitalize">{listing.city}</span>
                    </div>
                  )}
                </div>
                <div className="text-right shrink-0">
                  <div className="text-2xl font-bold text-[var(--primary)] flex items-baseline gap-2 justify-end">
                    {formatPrice(listing.price)}{listing.listing_type === "rent" ? <span className="text-base font-normal">/mese</span> : ""}
                    <PriceChangeBadge
                      price={listing.price}
                      pricePrevious={listing.price_previous}
                      priceChangedAt={listing.price_changed_at}
                      size="md"
                    />
                  </div>
                  {listing.price_previous != null && listing.price != null && listing.price_previous !== listing.price && (
                    <div className="text-sm text-[var(--muted-foreground)] line-through">
                      {formatPrice(listing.price_previous)}
                    </div>
                  )}
                  {listing.price_per_sqm && (
                    <div className="text-sm text-[var(--muted-foreground)]">{formatPrice(listing.price_per_sqm)}/m&sup2;</div>
                  )}
                </div>
              </div>
              <div className="flex flex-wrap gap-2 mt-3">
                <Badge>{listingTypeLabel(listing.listing_type)}</Badge>
                <Badge>{propertyTypeLabel(listing.property_type)}</Badge>
                {listing.energy_class && <Badge className={energyClassColor(listing.energy_class)}>Classe {listing.energy_class}</Badge>}
                {listing.condition && <Badge variant="outline">{conditionLabel(listing.condition)}</Badge>}
                {listing.is_auction && <AuctionBadge size="md" />}
              </div>
            </div>

            <PriceHistory listingId={listing.id} listingType={listing.listing_type} />

            {/* Key Facts */}
            <div>
              <h2 className="text-base font-bold mb-3">Caratteristiche principali</h2>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  { icon: FACT_ICONS.area, label: "Superficie", value: listing.area_sqm ? formatArea(listing.area_sqm) : null },
                  { icon: FACT_ICONS.rooms, label: "Locali", value: listing.rooms ? `${listing.rooms}` : null },
                  { icon: FACT_ICONS.bathrooms, label: "Bagni", value: listing.bathrooms ? `${listing.bathrooms}` : null },
                  { icon: FACT_ICONS.floor, label: "Piano", value: listing.floor ? floorLabel(listing.floor) : null },
                ].filter(f => f.value).map(({ icon: Icon, label, value }) => (
                  <div key={label} className="rounded-[var(--radius-md)] border border-[var(--border)] p-3 text-center">
                    <Icon className="h-5 w-5 mx-auto mb-1 text-[var(--primary)]" aria-hidden />
                    <div className="text-base font-bold">{value}</div>
                    <div className="text-[11px] text-[var(--muted-foreground)]">{label}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Features */}
            {presentAmenities(listing).length > 0 && (
              <div>
                <h2 className="text-base font-bold mb-3">Dotazioni</h2>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {presentAmenities(listing).map(({ key, label, icon: Icon }) => (
                    <div key={key} className="flex items-center gap-2 px-3 py-2 rounded-[var(--radius-sm)] bg-[var(--primary-light)] text-sm font-medium">
                      <Icon className="h-4 w-4 text-[var(--primary)]" aria-hidden /> {label}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Description */}
            {listing.description && (
              <div>
                <h2 className="text-base font-bold mb-3">Descrizione</h2>
                <p className="text-sm text-[var(--muted-foreground)] leading-relaxed whitespace-pre-line">{listing.description}</p>
              </div>
            )}

            {/* Map */}
            {listing.lat && listing.lng && (
              <div>
                <h2 className="text-base font-bold mb-3">Posizione</h2>
                <div className="rounded-[var(--radius-lg)] overflow-hidden border border-[var(--border)]">
                  <iframe
                    src={`https://www.openstreetmap.org/export/embed.html?bbox=${listing.lng - 0.01},${listing.lat - 0.007},${listing.lng + 0.01},${listing.lat + 0.007}&layer=mapnik&marker=${listing.lat},${listing.lng}`}
                    className="w-full h-64 border-0"
                    loading="lazy"
                  />
                </div>
              </div>
            )}
          </div>

          {/* Sidebar */}
          <div className="space-y-5">
            {/* Sources */}
            <div className="rounded-[var(--radius-lg)] border border-[var(--border)] p-5" style={{ boxShadow: "var(--card-shadow)" }}>
              <h3 className="font-bold mb-3 flex items-center gap-2">
                <Layers className="h-4 w-4 text-[var(--primary)]" />
                Visto su {listing.sources.length} {listing.sources.length === 1 ? "portale" : "portali"}
              </h3>
              <div className="space-y-2">
                {listing.sources.map((source) => (
                  <a key={source.id} href={source.source_url} target="_blank" rel="noopener noreferrer"
                    className="flex items-center justify-between p-3 rounded-[var(--radius-md)] border border-[var(--border)] hover:border-[var(--primary)] hover:bg-[var(--primary-light)] transition-all">
                    <div>
                      <Badge size="sm" className={`${portalColor(source.source_portal)} text-white`}>{portalLabel(source.source_portal)}</Badge>
                      {source.price_on_source && <div className="text-sm font-semibold mt-1">{formatPrice(source.price_on_source)}</div>}
                    </div>
                    <ExternalLink className="h-4 w-4 text-[var(--muted-foreground)]" />
                  </a>
                ))}
              </div>
            </div>

            {/* Details */}
            <div className="rounded-[var(--radius-lg)] border border-[var(--border)] p-5" style={{ boxShadow: "var(--card-shadow)" }}>
              <h3 className="font-bold mb-3">Dettagli</h3>
              <dl className="space-y-2.5 text-sm">
                {([
                  [FACT_ICONS.bedrooms, "Camere da letto", listing.bedrooms ? `${listing.bedrooms}` : null],
                  [FACT_ICONS.heating, "Riscaldamento", listing.heating],
                  [FACT_ICONS.condition, "Stato", listing.condition ? conditionLabel(listing.condition) : null],
                  [FACT_ICONS.condominiumFees, "Spese condominiali", listing.condominium_fees ? `${formatPrice(listing.condominium_fees)}/mese` : null],
                  [FACT_ICONS.yearBuilt, "Anno", listing.year_built ? `${listing.year_built}` : null],
                  [FACT_ICONS.totalFloors, "Piani totali", listing.total_floors ? `${listing.total_floors}` : null],
                ] as const).filter(([, , value]) => value).map(([Icon, label, value]) => (
                  <div key={label} className="flex justify-between gap-3">
                    <dt className="flex items-center gap-1.5 text-[var(--muted-foreground)]">
                      <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden />
                      {label}
                    </dt>
                    <dd className="font-medium text-right">{value}</dd>
                  </div>
                ))}
              </dl>
            </div>

            {/* Timestamps */}
            <div className="text-xs text-[var(--muted-foreground)] space-y-1 px-1">
              <PublishedAt date={listing.publication_date} className="text-sm text-[var(--foreground)]" iconClassName="h-3.5 w-3.5" />
              <div className="flex items-center gap-1">
                <Clock className="h-3 w-3 shrink-0" aria-hidden />
                Primo avvistamento: {seenAgo(listing.first_seen_at)}
              </div>
              <div className="flex items-center gap-1">
                <Clock className="h-3 w-3 shrink-0" aria-hidden />
                Ultimo aggiornamento: {seenAgo(listing.last_seen_at)}
              </div>
            </div>
          </div>
        </div>

        {/* Lightbox */}
        <ImageLightbox
          images={lightboxImages}
          initialIndex={lightboxIndex}
          open={lightboxOpen}
          onClose={() => setLightboxOpen(false)}
          title={lightboxSource === "plans" ? "Planimetria" : listing.title}
        />

        {/* Similar Listings */}
        {similar && similar.length > 0 && (
          <section className="mt-12 pt-8 border-t border-[var(--border)]">
            <h2 className="text-xl font-bold mb-5">Annunci simili a <span className="capitalize">{listing.city}</span></h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {similar.slice(0, 6).map((l) => (
                <ListingCard key={l.id} listing={l} />
              ))}
            </div>
          </section>
        )}
      </div>
    </>
  );
}
