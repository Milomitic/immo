"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useQueryState, parseAsString } from "nuqs";
import { useMapMarkers } from "@/hooks/useListings";
import { formatArea, formatPrice, roomsLabel } from "@/lib/utils";
import { Building2, List as ListIcon, MapPin, Pencil, X, Check } from "lucide-react";
import { useSearchParams } from "next/navigation";
import type { ListingSearchParams } from "@/lib/types";
import { filtersToParams, useListingFilters } from "@/components/search/FilterFields";
import { MapFilters } from "@/components/map/MapFilters";
import { ActiveFilters } from "@/components/search/ActiveFilters";

/**
 * Encode/decode the polygon URL param. Format: "lat,lng;lat,lng;...".
 * Vertices are stored to 5 decimals — about 1 m of resolution, plenty
 * for a hand-drawn perimeter and keeps the URL short.
 */
function encodePolygon(points: [number, number][]): string {
  return points.map(([la, ln]) => `${la.toFixed(5)},${ln.toFixed(5)}`).join(";");
}
function decodePolygon(s: string | null): [number, number][] | null {
  if (!s) return null;
  const pts: [number, number][] = [];
  for (const chunk of s.split(";")) {
    const [la, ln] = chunk.split(",").map(parseFloat);
    if (Number.isFinite(la) && Number.isFinite(ln)) pts.push([la, ln]);
  }
  return pts.length >= 3 ? pts : null;
}

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
  const [q] = useQueryState("q", parseAsString);
  const [bbox, setBbox] = useQueryState("bbox", parseAsString);
  const [polygonStr, setPolygonStr] = useQueryState("polygon", parseAsString);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Build a /search href that carries every current filter param. ``bbox``
  // is intentionally excluded — the search list shouldn't be clipped to
  // whatever viewport the user happens to have on the map.
  const searchParams = useSearchParams();
  const searchHref = useMemo(() => {
    const out = new URLSearchParams();
    searchParams.forEach((v, k) => {
      if (k !== "bbox") out.set(k, v);
    });
    return `/search${out.size > 0 ? `?${out.toString()}` : ""}`;
  }, [searchParams]);

  // --- Drawing state (local; only the *finalised* polygon goes in URL).
  const [drawingMode, setDrawingMode] = useState(false);
  const [drawingPoints, setDrawingPoints] = useState<[number, number][]>([]);

  const polygon = useMemo(() => decodePolygon(polygonStr), [polygonStr]);

  const handleAddVertex = useCallback((latlng: [number, number]) => {
    setDrawingPoints((prev) => [...prev, latlng]);
  }, []);

  const handleStartDrawing = useCallback(() => {
    setDrawingMode(true);
    setDrawingPoints([]);
    // Clear any previous polygon so the user starts from a clean slate.
    setPolygonStr(null);
  }, [setPolygonStr]);

  const handleFinishDrawing = useCallback(() => {
    if (drawingPoints.length >= 3) {
      setPolygonStr(encodePolygon(drawingPoints));
    }
    setDrawingMode(false);
    setDrawingPoints([]);
  }, [drawingPoints, setPolygonStr]);

  const handleCancelDrawing = useCallback(() => {
    setDrawingMode(false);
    setDrawingPoints([]);
  }, []);

  const handleClearPolygon = useCallback(() => {
    setPolygonStr(null);
  }, [setPolygonStr]);

  // Esc shortcut while drawing — quick cancel.
  useEffect(() => {
    if (!drawingMode) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") handleCancelDrawing();
      else if (e.key === "Enter") handleFinishDrawing();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [drawingMode, handleCancelDrawing, handleFinishDrawing]);

  const params: ListingSearchParams & { limit: number } = {
    ...filtersToParams(values),
    q: q || undefined,
    // When a polygon is set, send only the polygon — bbox would over-
    // include and the server would have to filter it twice. The polygon's
    // own bounding box is computed server-side as a SQL pre-filter.
    bbox: polygon ? undefined : (bbox || undefined),
    polygon: polygonStr || undefined,
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

          {/* Draw / Cancel-perimeter controls */}
          {!drawingMode && !polygon && (
            <button
              onClick={handleStartDrawing}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-sm)] border border-[var(--border)] text-xs font-medium hover:bg-[var(--muted)] transition-colors"
              title="Disegna un perimetro per delimitare la ricerca"
            >
              <Pencil className="h-3.5 w-3.5" />
              Disegna area
            </button>
          )}
          {drawingMode && (
            <>
              <button
                onClick={handleFinishDrawing}
                disabled={drawingPoints.length < 3}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-sm)] bg-[var(--primary)] text-[var(--primary-foreground)] text-xs font-semibold disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90 transition-opacity"
                title="Termina il disegno (Invio)"
              >
                <Check className="h-3.5 w-3.5" />
                Termina ({drawingPoints.length})
              </button>
              <button
                onClick={handleCancelDrawing}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-sm)] border border-[var(--border)] text-xs font-medium hover:bg-[var(--muted)] transition-colors"
                title="Annulla (Esc)"
              >
                <X className="h-3.5 w-3.5" />
                Annulla
              </button>
            </>
          )}
          {!drawingMode && polygon && (
            <button
              onClick={handleClearPolygon}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-sm)] border border-[var(--primary)] text-[var(--primary)] text-xs font-semibold hover:bg-[var(--primary)]/5 transition-colors"
              title="Rimuovi il perimetro"
            >
              <X className="h-3.5 w-3.5" />
              Area disegnata
            </button>
          )}

          <span className="text-xs text-[var(--muted-foreground)] ml-auto">
            {drawingMode
              ? `Clicca sulla mappa per aggiungere vertici (min 3, Invio per terminare)`
              : isLoading
              ? "Caricamento..."
              : `${data?.total ?? 0} annunci${
                  data?.truncated ? ` (primi ${markers.length})` : ""
                }`}
          </span>

          {/* Mirror of ResultsHeader's "Mappa" CTA — keeps /map ↔ /search
              navigation symmetric, propagates filters (incl. polygon). */}
          <Link
            href={searchHref}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-sm)] border border-[var(--border)] text-xs font-medium hover:bg-[var(--muted)] transition-colors"
            title="Vedi gli stessi annunci in lista"
          >
            <ListIcon className="h-3.5 w-3.5" />
            Lista
          </Link>
        </div>
        {/* Chip-bar with all active filters — same component used on
            /search so chips look identical across views and an X removes
            a single filter without dismissing the others. */}
        <div className="mt-2">
          <ActiveFilters />
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
            drawingMode={drawingMode}
            drawingPoints={drawingPoints}
            polygon={polygon}
            onAddVertex={handleAddVertex}
          />
        </div>
      </div>
    </div>
  );
}
