"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useQueryState, parseAsString } from "nuqs";
import { useMapMarkers } from "@/hooks/useListings";
import { cn } from "@/lib/utils";
import { List as ListIcon, Map as MapIcon, Pencil, X, Check } from "lucide-react";
import { useSearchParams } from "next/navigation";
import type { ListingSearchParams } from "@/lib/types";
import { filtersToParams, useListingFilters } from "@/components/search/FilterFields";
import { MapFiltersButton, MapFiltersPanel } from "@/components/map/MapFilters";
import { MapListItem } from "@/components/map/MapListItem";
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
  // Row under the pointer (highlights its pin) and the row opened in place.
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  // Phones get one panel at a time; md+ shows list and map side by side.
  const [mobileView, setMobileView] = useState<"map" | "list">("map");
  const closeFilters = useCallback(() => setFiltersOpen(false), []);
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

  // A pin click opens its row; scrolling waits for the row to render open.
  const scrollToRow = useRef<string | null>(null);
  const handleMarkerClick = useCallback((id: string) => {
    scrollToRow.current = id;
    setExpandedId(id);
  }, []);
  useEffect(() => {
    if (!expandedId || scrollToRow.current !== expandedId) return;
    scrollToRow.current = null;
    document.getElementById(`map-list-${expandedId}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [expandedId]);
  const toggleRow = useCallback((id: string) => setExpandedId((cur) => (cur === id ? null : id)), []);

  const { listingType } = values;
  const { setListingType } = setters;

  return (
    <div className="h-[calc(100dvh-3.5rem)] flex flex-col">
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

          {/* The other filters open as a sub-bar below this one. */}
          <MapFiltersButton open={filtersOpen} onToggle={() => setFiltersOpen((o) => !o)} />

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

          <div className="md:hidden flex rounded-[var(--radius-sm)] overflow-hidden border border-[var(--border)]">
            {(["map", "list"] as const).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setMobileView(v)}
                aria-pressed={mobileView === v}
                className={cn(
                  "flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium",
                  v === "list" && "border-l border-[var(--border)]",
                  mobileView === v ? "bg-[var(--primary)] text-[var(--primary-foreground)]" : "hover:bg-[var(--muted)]",
                )}
              >
                {v === "map" ? <MapIcon className="h-3.5 w-3.5" /> : <ListIcon className="h-3.5 w-3.5" />}
                {v === "map" ? "Mappa" : "Elenco"}
              </button>
            ))}
          </div>

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

      {filtersOpen && <MapFiltersPanel onClose={closeFilters} />}

      {/* Split layout */}
      <div className="flex-1 flex overflow-hidden min-h-0">
        {/* Left: scrollable list */}
        <div
          className={cn(
            "shrink-0 border-r border-[var(--border)] overflow-y-auto md:block md:w-[28rem] xl:w-[30rem]",
            mobileView === "list" ? "block w-full" : "hidden",
          )}
        >
          {markers.length === 0 && !isLoading && (
            <div className="p-6 text-center text-sm text-[var(--muted-foreground)]">
              Nessun annuncio in questa area.
              <br />
              Sposta la mappa o allenta i filtri per cercare.
            </div>
          )}
          {markers.map((m) => (
            <MapListItem
              key={m.id}
              marker={m}
              mode={expandedId === m.id ? "expanded" : expandedId ? "compact" : "normal"}
              highlighted={hoverId === m.id}
              onToggle={() => toggleRow(m.id)}
              onHover={setHoverId}
            />
          ))}
        </div>

        {/* Right: map */}
        <div className={cn("flex-1 relative min-w-0 md:block", mobileView === "map" ? "block" : "hidden")}>
          <MapView
            markers={markers}
            center={DEFAULT_CENTER}
            zoom={DEFAULT_ZOOM}
            onViewportChange={handleViewportChange}
            selectedId={hoverId ?? expandedId}
            layoutKey={`${filtersOpen}-${mobileView}`}
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
