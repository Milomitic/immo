"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import {
  ArrowRight, Building2, ChevronLeft, ChevronRight, ChevronUp, ExternalLink,
  GripHorizontal, Map as MapIcon, MapPin, Maximize2, Minimize2,
} from "lucide-react";
import { useListingDetail } from "@/hooks/useListings";
import type { ListingMarker } from "@/lib/types";
import {
  cn, conditionLabel, energyClassColor, floorLabel, formatArea, formatPrice,
  imageVariant, portalLabel, publishedSince, roomsLabel,
} from "@/lib/utils";
import { AuctionBadge } from "@/components/listings/AuctionBadge";
import { FavoriteButton } from "@/components/listings/FavoriteButton";
import { PriceChangeBadge } from "@/components/listings/PriceChangeBadge";

export type MapListItemMode = "normal" | "compact" | "expanded";

const fullDate = new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "long", year: "numeric" });

function PostedAt({ date, className }: { date: string | null; className?: string }) {
  const since = publishedSince(date);
  if (!since || !date) return null;
  return (
    <span
      className={cn("shrink-0 text-[10px] text-[var(--muted-foreground)] whitespace-nowrap", className)}
      title={`Pubblicato il ${fullDate.format(new Date(`${date.slice(0, 10)}T00:00:00`))}`}
    >
      Pubblicato {since}
    </span>
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
              {expanded && <ChevronUp className="h-4 w-4 ml-auto text-[var(--muted-foreground)]" aria-hidden />}
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
            {/* Bottom line: size on the left, publication age bottom-right. */}
            <div className="flex items-end justify-between gap-2 mt-auto pt-0.5">
              <span className="text-xs text-[var(--muted-foreground)]">{m.area_sqm ? formatArea(m.area_sqm) : ""}</span>
              <PostedAt date={m.publication_date} />
            </div>
          </div>
        )}
      </div>

      {expanded && <ListingQuickLook id={m.id} onCollapse={onToggle} />}
    </div>
  );
}

const DEFAULT_HEIGHT = 420;
const MIN_HEIGHT = 200;
const RESIZE_STEP = 40;

function maxHeight(): number {
  return typeof window === "undefined" ? 800 : Math.round(window.innerHeight * 0.8);
}

/** The opened row: photos and the main facts, resizable by dragging the
 *  grip (or with ↑/↓ on it), with the full page one click away. */
function ListingQuickLook({ id, onCollapse }: { id: string; onCollapse: () => void }) {
  const { data: listing, isLoading, isError } = useListingDetail(id);
  const [height, setHeight] = useState(DEFAULT_HEIGHT);
  const [photo, setPhoto] = useState(0);
  const drag = useRef<{ startY: number; startHeight: number } | null>(null);

  const clamp = (h: number) => Math.max(MIN_HEIGHT, Math.min(maxHeight(), h));
  const maximized = height >= maxHeight() - 2;

  const photos = listing?.images ?? [];
  const plans = listing?.floor_plans ?? [];
  const gallery = [...photos, ...plans];
  const current = gallery.length ? photo % gallery.length : 0;
  const isPlan = current >= photos.length;

  const facts = listing
    ? [
        ["Superficie", listing.area_sqm ? formatArea(listing.area_sqm) : null],
        ["Locali", listing.rooms ? `${listing.rooms}` : null],
        ["Bagni", listing.bathrooms ? `${listing.bathrooms}` : null],
        ["Piano", listing.floor ? floorLabel(listing.floor) : null],
        ["€/m²", listing.price_per_sqm ? formatPrice(listing.price_per_sqm) : null],
        ["Stato", listing.condition ? conditionLabel(listing.condition) : null],
        ["Anno", listing.year_built ? `${listing.year_built}` : null],
        ["Spese cond.", listing.condominium_fees ? `${formatPrice(listing.condominium_fees)}/mese` : null],
      ].filter((f): f is [string, string] => Boolean(f[1]))
    : [];
  const features = listing
    ? ([
        ["Ascensore", listing.has_elevator],
        ["Balcone", listing.has_balcony],
        ["Terrazzo", listing.has_terrace],
        ["Garage / box", listing.has_garage],
        ["Giardino", listing.has_garden],
      ] as const).filter(([, v]) => v === true).map(([label]) => label)
    : [];

  return (
    <div className="px-3 pb-2">
      <div
        style={{ height }}
        className="overflow-y-auto overscroll-contain rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--background)]"
      >
        {isLoading && <div className="p-4 text-sm text-[var(--muted-foreground)] animate-pulse">Caricamento dettagli…</div>}
        {isError && <div className="p-4 text-sm text-[var(--destructive)]">Dettagli non disponibili.</div>}

        {listing && (
          <>
            {gallery.length > 0 && (
              <div className="relative aspect-[16/10] bg-[var(--muted)]">
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
                  {facts.map(([label, value]) => (
                    <div key={label} className="rounded-[var(--radius-sm)] bg-[var(--muted)] px-2 py-1.5">
                      <dt className="text-[10px] text-[var(--muted-foreground)]">{label}</dt>
                      <dd className="text-xs font-semibold">{value}</dd>
                    </div>
                  ))}
                  {listing.energy_class && (
                    <div className="rounded-[var(--radius-sm)] bg-[var(--muted)] px-2 py-1.5">
                      <dt className="text-[10px] text-[var(--muted-foreground)]">Classe</dt>
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
                  {features.map((f) => (
                    <span key={f} className="px-2 py-0.5 rounded-full border border-[var(--border)] text-[11px]">{f}</span>
                  ))}
                </div>
              )}

              {listing.description && (
                <p className="text-xs leading-relaxed whitespace-pre-line text-[var(--foreground)]/90">{listing.description}</p>
              )}

              <p className="text-[11px] text-[var(--muted-foreground)]">
                {portalLabel(listing.source_portal)}
                {listing.sources.length > 1 ? ` + altre ${listing.sources.length - 1} fonti` : ""}
                {listing.publication_date
                  ? ` · pubblicato il ${fullDate.format(new Date(`${listing.publication_date.slice(0, 10)}T00:00:00`))}`
                  : ""}
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
        }}
        onPointerMove={(e) => {
          if (drag.current) setHeight(clamp(drag.current.startHeight + e.clientY - drag.current.startY));
        }}
        onPointerUp={() => {
          drag.current = null;
        }}
        onDoubleClick={() => setHeight(maximized ? DEFAULT_HEIGHT : maxHeight())}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") setHeight((h) => clamp(h + RESIZE_STEP));
          else if (e.key === "ArrowUp") setHeight((h) => clamp(h - RESIZE_STEP));
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
          onClick={() => setHeight(maximized ? DEFAULT_HEIGHT : maxHeight())}
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
