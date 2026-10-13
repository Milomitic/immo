"use client";

import Link from "next/link";
import { useLayoutEffect, useRef, useState } from "react";
import {
  ArrowRight, Building2, ChevronLeft, ChevronRight, ChevronUp, ExternalLink,
  GripHorizontal, Map as MapIcon, MapPin, Maximize2, Minimize2,
} from "lucide-react";
import { useListingDetail } from "@/hooks/useListings";
import type { ListingMarker } from "@/lib/types";
import {
  cn, conditionLabel, energyClassColor, floorLabel, formatArea, formatPrice,
  imageVariant, portalColor, portalLabel, roomsLabel,
} from "@/lib/utils";
import { AuctionBadge } from "@/components/listings/AuctionBadge";
import { FavoriteButton } from "@/components/listings/FavoriteButton";
import { PriceChangeBadge } from "@/components/listings/PriceChangeBadge";
import { PublishedAt } from "@/components/listings/PublishedAt";
import { KeyFacts } from "@/components/listings/ListingFeatures";
import { FACT_ICONS, presentAmenities } from "@/components/listings/featureIcons";

export type MapListItemMode = "normal" | "compact" | "expanded";

function PortalLabel({ portal }: { portal: string }) {
  if (!portal) return null;
  return (
    <span
      className={cn(
        "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold leading-none text-white",
        portalColor(portal),
      )}
      title={`Annuncio da ${portalLabel(portal)}`}
    >
      {portalLabel(portal)}
    </span>
  );
}

function PostedAt({ date, className }: { date: string | null; className?: string }) {
  return (
    <PublishedAt
      date={date}
      className={cn("shrink-0 text-xs text-[var(--muted-foreground)]", className)}
      iconClassName="h-3.5 w-3.5"
    />
  );
}

interface MapListItemProps {
  marker: ListingMarker;
  mode: MapListItemMode;
  highlighted: boolean;
  onToggle: () => void;
  onHover: (id: string | null) => void;
}

/**
 * A row of the map's list. Clicking it opens the listing in place (a quick
 * look with photos and details) while the other rows shrink; the full page
 * stays one link away.
 */
export function MapListItem({ marker: m, mode, highlighted, onToggle, onHover }: MapListItemProps) {
  const compact = mode === "compact";
  const expanded = mode === "expanded";

  return (
    <div id={`map-list-${m.id}`} className={cn("border-b border-[var(--border)]", expanded && "bg-[var(--muted)]")}>
      <div
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onToggle();
          }
        }}
        onMouseEnter={() => onHover(m.id)}
        onMouseLeave={() => onHover(null)}
        className={cn(
          "flex gap-3 cursor-pointer transition-colors hover:bg-[var(--muted)] focus-visible:outline-2 focus-visible:outline-[var(--primary)] focus-visible:-outline-offset-2",
          compact ? "px-3 py-1.5" : "p-3",
          highlighted && !expanded && "bg-[var(--muted)]",
        )}
      >
        <div
          className={cn(
            "shrink-0 rounded-[var(--radius-sm)] overflow-hidden bg-[var(--muted)] transition-all",
            compact ? "w-14 h-10" : "w-28 h-20",
          )}
        >
          {m.thumbnail ? (
            <img
              src={imageVariant(m.thumbnail, "card")}
              alt=""
              referrerPolicy="no-referrer"
              loading="lazy"
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-[var(--muted-foreground)]">
              <Building2 className={compact ? "h-4 w-4 opacity-40" : "h-6 w-6 opacity-40"} />
            </div>
          )}
        </div>

        {compact ? (
          <div className="flex-1 min-w-0 flex items-center gap-2">
            <span className="text-sm font-bold text-[var(--primary)] shrink-0">
              {m.price ? formatPrice(m.price) : "Su richiesta"}
            </span>
            {m.is_auction && <AuctionBadge />}
            <PortalLabel portal={m.source_portal} />
            <span className="text-xs truncate text-[var(--muted-foreground)]">{m.title}</span>
            <PostedAt date={m.publication_date} className="ml-auto" />
          </div>
        ) : (
          <div className="flex-1 min-w-0 flex flex-col">
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-[var(--primary)]">
                {m.price ? formatPrice(m.price) : "Prezzo su richiesta"}
              </span>
              {m.is_auction && <AuctionBadge />}
              <span className="ml-auto flex items-center gap-1.5">
                <PortalLabel portal={m.source_portal} />
                {expanded && <ChevronUp className="h-4 w-4 text-[var(--muted-foreground)]" aria-hidden />}
              </span>
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
            {/* Bottom line: rooms and size on the left, publication age
                bottom-right. */}
            <div className="flex items-end justify-between gap-2 mt-auto pt-0.5">
              <span className="flex items-center text-xs text-[var(--muted-foreground)]">
                <KeyFacts listing={m} />
              </span>
              <PostedAt date={m.publication_date} />
            </div>
          </div>
        )}
      </div>

      {expanded && <ListingQuickLook id={m.id} onCollapse={onToggle} />}
    </div>
  );
}

// Used until the details are in; then the box fits them (see below).
const DEFAULT_HEIGHT = 560;
const MIN_HEIGHT = 200;
const RESIZE_STEP = 40;
// Below the facts, show the start of the description: a cue to scroll.
const DESCRIPTION_PEEK = 48;

function maxHeight(): number {
  return typeof window === "undefined" ? 800 : Math.round(window.innerHeight * 0.8);
}

/** The opened row: photos and the main facts, resizable by dragging the
 *  grip (or with ↑/↓ on it), with the full page one click away. */
function ListingQuickLook({ id, onCollapse }: { id: string; onCollapse: () => void }) {
  const { data: listing, isLoading, isError } = useListingDetail(id);
  const [height, setHeight] = useState(DEFAULT_HEIGHT);
  // The opening height, fitted to the content: "Riduci" goes back to it.
  const [fitHeight, setFitHeight] = useState(DEFAULT_HEIGHT);
  const [photo, setPhoto] = useState(0);
  const drag = useRef<{ startY: number; startHeight: number } | null>(null);
  const infoEnd = useRef<HTMLDivElement>(null);
  const userSized = useRef(false);

  const clamp = (h: number) => Math.max(MIN_HEIGHT, Math.min(maxHeight(), h));
  const maximized = height >= maxHeight() - 2;
  const resize = (h: number) => {
    userSized.current = true;
    setHeight(clamp(h));
  };

  // Open tall enough that photo, price, facts and features all show without
  // scrolling, whatever their number. The gallery has a fixed aspect ratio,
  // so the layout is final before any image loads; measured before paint,
  // so there's no jump.
  useLayoutEffect(() => {
    if (!listing || !infoEnd.current) return;
    const fitted = clamp(infoEnd.current.offsetTop + (listing.description ? DESCRIPTION_PEEK : 8));
    setFitHeight(fitted);
    if (!userSized.current) setHeight(fitted);
  }, [listing]);

  const photos = listing?.images ?? [];
  const plans = listing?.floor_plans ?? [];
  const gallery = [...photos, ...plans];
  const current = gallery.length ? photo % gallery.length : 0;
  const isPlan = current >= photos.length;

  const facts = listing
    ? ([
        ["Superficie", FACT_ICONS.area, listing.area_sqm ? formatArea(listing.area_sqm) : null],
        ["Locali", FACT_ICONS.rooms, listing.rooms ? `${listing.rooms}` : null],
        ["Bagni", FACT_ICONS.bathrooms, listing.bathrooms ? `${listing.bathrooms}` : null],
        ["Piano", FACT_ICONS.floor, listing.floor ? floorLabel(listing.floor) : null],
        ["€/m²", FACT_ICONS.pricePerSqm, listing.price_per_sqm ? formatPrice(listing.price_per_sqm) : null],
        ["Stato", FACT_ICONS.condition, listing.condition ? conditionLabel(listing.condition) : null],
        ["Anno", FACT_ICONS.yearBuilt, listing.year_built ? `${listing.year_built}` : null],
        ["Spese cond.", FACT_ICONS.condominiumFees, listing.condominium_fees ? `${formatPrice(listing.condominium_fees)}/mese` : null],
      ] as const).filter((f) => Boolean(f[2]))
    : [];
  const features = listing ? presentAmenities(listing) : [];
  const EnergyIcon = FACT_ICONS.energyClass;

  return (
    <div className="px-3 pb-2">
      <div
        style={{ height }}
        className="relative overflow-y-auto overscroll-contain rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--background)]"
      >
        {isLoading && <div className="p-4 text-sm text-[var(--muted-foreground)] animate-pulse">Caricamento dettagli…</div>}
        {isError && <div className="p-4 text-sm text-[var(--destructive)]">Dettagli non disponibili.</div>}

        {listing && (
          <>
            {gallery.length > 0 && (
              <div className="relative aspect-[2/1] bg-[var(--muted)]">
                <img
                  src={imageVariant(gallery[current], "full")}
                  alt={isPlan ? "Planimetria" : `Foto ${current + 1}`}
                  referrerPolicy="no-referrer"
                  className={cn("w-full h-full", isPlan ? "object-contain bg-white" : "object-cover")}
                />
                {isPlan && (
                  <span className="absolute top-2 left-2 flex items-center gap-1 px-2 py-0.5 rounded-full bg-[var(--primary)] text-[var(--primary-foreground)] text-[11px] font-semibold">
                    <MapIcon className="h-3 w-3" /> Planimetria
                  </span>
                )}
                {gallery.length > 1 && (
                  <>
                    <button
                      type="button"
                      onClick={() => setPhoto((current - 1 + gallery.length) % gallery.length)}
                      className="absolute left-2 top-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-black/50 text-white flex items-center justify-center hover:bg-black/70"
                      aria-label="Foto precedente"
                    >
                      <ChevronLeft className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setPhoto((current + 1) % gallery.length)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-black/50 text-white flex items-center justify-center hover:bg-black/70"
                      aria-label="Foto successiva"
                    >
                      <ChevronRight className="h-4 w-4" />
                    </button>
                    <span className="absolute bottom-2 right-2 px-2 py-0.5 rounded-full bg-black/55 text-white text-[11px]">
                      {current + 1} / {gallery.length}
                    </span>
                  </>
                )}
                <FavoriteButton listingId={listing.id} className="absolute top-2 right-2" />
              </div>
            )}

            <div className="p-3 space-y-3">
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-lg font-bold text-[var(--primary)]">
                    {formatPrice(listing.price)}
                    {listing.listing_type === "rent" && listing.price ? "/mese" : ""}
                  </span>
                  <PriceChangeBadge
                    price={listing.price}
                    pricePrevious={listing.price_previous}
                    priceChangedAt={listing.price_changed_at}
                  />
                  {listing.is_auction && <AuctionBadge size="md" />}
                </div>
                <h3 className="text-sm font-semibold mt-1">{listing.title}</h3>
                {(listing.address || listing.zone) && (
                  <p className="text-xs text-[var(--muted-foreground)] mt-0.5">
                    {[listing.address, listing.zone].filter(Boolean).join(", ")}
                  </p>
                )}
              </div>

              {facts.length > 0 && (
                <dl className="grid grid-cols-3 gap-2">
                  {facts.map(([label, Icon, value]) => (
                    <div key={label} className="rounded-[var(--radius-sm)] bg-[var(--muted)] px-2 py-1.5">
                      <dt className="flex items-center gap-1 text-[10px] text-[var(--muted-foreground)]">
                        <Icon className="h-3 w-3 shrink-0" aria-hidden />
                        {label}
                      </dt>
                      <dd className="text-xs font-semibold">{value}</dd>
                    </div>
                  ))}
                  {listing.energy_class && (
                    <div className="rounded-[var(--radius-sm)] bg-[var(--muted)] px-2 py-1.5">
                      <dt className="flex items-center gap-1 text-[10px] text-[var(--muted-foreground)]">
                        <EnergyIcon className="h-3 w-3 shrink-0" aria-hidden />
                        Classe
                      </dt>
                      <dd>
                        <span className={cn("text-xs font-bold px-1.5 rounded", energyClassColor(listing.energy_class))}>
                          {listing.energy_class}
                        </span>
                      </dd>
                    </div>
                  )}
                </dl>
              )}

              {features.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {features.map(({ key, label, icon: Icon }) => (
                    <span key={key} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-[var(--border)] text-[11px]">
                      <Icon className="h-3 w-3 text-[var(--primary)]" aria-hidden />
                      {label}
                    </span>
                  ))}
                </div>
              )}

              {/* End of the always-visible part (see the fit above). */}
              <div ref={infoEnd} aria-hidden />

              {listing.description && (
                <p className="text-xs leading-relaxed whitespace-pre-line text-[var(--foreground)]/90">{listing.description}</p>
              )}

              <p className="flex flex-wrap items-center gap-x-2 text-[11px] text-[var(--muted-foreground)]">
                <span>
                  {portalLabel(listing.source_portal)}
                  {listing.sources.length > 1 ? ` + altre ${listing.sources.length - 1} fonti` : ""}
                </span>
                <PublishedAt date={listing.publication_date} />
              </p>
            </div>
          </>
        )}
      </div>

      {/* Resize grip: drag, ↑/↓, or double-click to toggle full height. */}
      <div
        role="separator"
        aria-orientation="horizontal"
        aria-label="Ridimensiona l'anteprima"
        aria-valuenow={height}
        aria-valuemin={MIN_HEIGHT}
        tabIndex={0}
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId);
          drag.current = { startY: e.clientY, startHeight: height };
          userSized.current = true;
        }}
        onPointerMove={(e) => {
          if (drag.current) setHeight(clamp(drag.current.startHeight + e.clientY - drag.current.startY));
        }}
        onPointerUp={() => {
          drag.current = null;
        }}
        onDoubleClick={() => resize(maximized ? fitHeight : maxHeight())}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") resize(height + RESIZE_STEP);
          else if (e.key === "ArrowUp") resize(height - RESIZE_STEP);
          else return;
          e.preventDefault();
        }}
        className="flex justify-center py-1 cursor-row-resize touch-none text-[var(--muted-foreground)] hover:text-[var(--foreground)] focus-visible:outline-2 focus-visible:outline-[var(--primary)] rounded"
        title="Trascina per ridimensionare (doppio clic: tutta altezza)"
      >
        <GripHorizontal className="h-4 w-4" />
      </div>

      <div className="flex items-center gap-2">
        <Link
          href={`/listing/${id}`}
          className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-sm)] bg-[var(--primary)] text-[var(--primary-foreground)] text-xs font-semibold hover:opacity-90"
        >
          Apri scheda completa <ArrowRight className="h-3.5 w-3.5" />
        </Link>
        {listing && (
          <a
            href={listing.listing_url}
            target="_blank"
            rel="noopener noreferrer"
            className="p-1.5 rounded-[var(--radius-sm)] border border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            title={`Vedi su ${portalLabel(listing.source_portal)}`}
            aria-label={`Vedi su ${portalLabel(listing.source_portal)}`}
          >
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        )}
        <button
          type="button"
          onClick={() => resize(maximized ? fitHeight : maxHeight())}
          className="p-1.5 rounded-[var(--radius-sm)] border border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
          aria-label={maximized ? "Riduci l'anteprima" : "Ingrandisci l'anteprima"}
          title={maximized ? "Riduci l'anteprima" : "Ingrandisci l'anteprima"}
        >
          {maximized ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
        </button>
        <button
          type="button"
          onClick={onCollapse}
          className="inline-flex items-center gap-1 px-2 py-1.5 rounded-[var(--radius-sm)] border border-[var(--border)] text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
        >
          <ChevronUp className="h-3.5 w-3.5" /> Chiudi
        </button>
      </div>
    </div>
  );
}
