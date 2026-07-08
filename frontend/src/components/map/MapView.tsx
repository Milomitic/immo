"use client";

import { useEffect } from "react";
import { MapContainer, TileLayer, Marker, Polygon, Polyline, CircleMarker, Popup, useMapEvents } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import Link from "next/link";
import type { ListingMarker } from "@/lib/types";
import { formatPrice } from "@/lib/utils";

L.Icon.Default.mergeOptions({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

function shortPrice(price: number | null): string {
  if (!price) return "—";
  if (price >= 1_000_000) return `€${(price / 1_000_000).toFixed(1)}M`;
  if (price >= 1_000) return `€${Math.round(price / 1_000)}k`;
  return `€${price}`;
}

function createPriceIcon(price: number | null, highlighted: boolean): L.DivIcon {
  const label = shortPrice(price);
  const bg = highlighted ? "#0f172a" : "#ffffff";
  const fg = highlighted ? "#ffffff" : "#0f172a";
  const border = highlighted ? "#0f172a" : "#d4d4d8";
  return L.divIcon({
    className: "",
    html: `<div style="background:${bg};color:${fg};border:1px solid ${border};border-radius:999px;padding:3px 9px;font-size:11px;font-weight:700;box-shadow:0 1px 3px rgba(0,0,0,0.25);white-space:nowrap;font-family:system-ui,sans-serif">${label}</div>`,
    iconSize: [50, 22],
    iconAnchor: [25, 11],
  });
}

interface ViewportSyncProps {
  onChange: (bbox: string) => void;
}

function emitBbox(map: L.Map, onChange: (bbox: string) => void) {
  const b = map.getBounds();
  // Guard: skip degenerate bounds (map not sized yet).
  const latSpan = Math.abs(b.getNorth() - b.getSouth());
  const lngSpan = Math.abs(b.getEast() - b.getWest());
  if (latSpan < 0.001 || lngSpan < 0.001) return;
  onChange(`${b.getSouth()},${b.getWest()},${b.getNorth()},${b.getEast()}`);
}

function ViewportSync({ onChange, enabled }: ViewportSyncProps & { enabled: boolean }) {
  const map = useMapEvents({
    moveend: () => {
      if (enabled) emitBbox(map, onChange);
    },
  });

  useEffect(() => {
    // Leaflet needs a frame to lay out the container at full size.
    // Without invalidateSize + raf, getBounds() returns a zero-area point.
    const raf = requestAnimationFrame(() => {
      map.invalidateSize();
      if (enabled) emitBbox(map, onChange);
    });
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  return null;
}

/**
 * Capture map clicks while drawing mode is on. Each click pushes a
 * vertex into the parent's polygon-points state. Hooks into Leaflet's
 * own click event so it doesn't conflict with marker clicks (Leaflet
 * fires `click` on the map only when no marker swallowed it).
 */
function DrawClickCapture({
  active,
  onAddVertex,
}: {
  active: boolean;
  onAddVertex: (latlng: [number, number]) => void;
}) {
  useMapEvents({
    click: (e) => {
      if (!active) return;
      onAddVertex([e.latlng.lat, e.latlng.lng]);
    },
  });
  return null;
}

interface MapViewProps {
  markers: ListingMarker[];
  center: [number, number];
  zoom: number;
  onViewportChange: (bbox: string) => void;
  selectedId?: string | null;
  onMarkerClick?: (id: string) => void;
  /** When true the map captures clicks as polygon vertices instead
      of acting normally; the bbox sync also pauses so panning while
      drawing doesn't refetch. */
  drawingMode?: boolean;
  /** Vertices currently being drawn (live polygon preview). */
  drawingPoints?: [number, number][];
  /** Finalised polygon (the perimeter the search uses). */
  polygon?: [number, number][] | null;
  /** Called for each click on the map while drawingMode is true. */
  onAddVertex?: (latlng: [number, number]) => void;
}

export default function MapView({
  markers,
  center,
  zoom,
  onViewportChange,
  selectedId,
  onMarkerClick,
  drawingMode = false,
  drawingPoints = [],
  polygon = null,
  onAddVertex,
}: MapViewProps) {
  // Visual style for the drawn perimeter — same primary blue as the rest
  // of the UI, slightly translucent so markers underneath stay readable.
  const polyStyle = { color: "#1d4ed8", weight: 2, fillColor: "#1d4ed8", fillOpacity: 0.10 };
  // Show either the in-progress polyline (drawing) or the closed polygon
  // (set). When drawingMode is on, each click becomes a vertex; double
  // click-to-finalize is handled in the parent via a button.
  return (
    <MapContainer
      center={center}
      zoom={zoom}
      scrollWheelZoom
      style={{
        width: "100%",
        height: "100%",
        cursor: drawingMode ? "crosshair" : undefined,
      }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {/* While drawing we don't refetch on every pan — would be confusing. */}
      <ViewportSync onChange={onViewportChange} enabled={!drawingMode} />
      <DrawClickCapture active={drawingMode} onAddVertex={onAddVertex ?? (() => {})} />

      {/* Closed polygon (filter is active) */}
      {polygon && polygon.length >= 3 && (
        <Polygon positions={polygon} pathOptions={polyStyle} />
      )}

      {/* In-progress drawing — polyline + vertex dots */}
      {drawingMode && drawingPoints.length > 0 && (
        <>
          <Polyline positions={drawingPoints} pathOptions={{ color: "#1d4ed8", weight: 2, dashArray: "4 4" }} />
          {drawingPoints.map((p, i) => (
            <CircleMarker
              key={i}
              center={p}
              radius={5}
              pathOptions={{ color: "#1d4ed8", fillColor: "#ffffff", fillOpacity: 1, weight: 2 }}
            />
          ))}
        </>
      )}

      {markers.map((m) => (
        <Marker
          key={m.id}
          position={[m.lat, m.lng]}
          icon={createPriceIcon(m.price, selectedId === m.id)}
          eventHandlers={{ click: () => onMarkerClick?.(m.id) }}
          zIndexOffset={selectedId === m.id ? 1000 : 0}
        >
          <Popup>
            <div style={{ width: 220 }}>
              {m.thumbnail && (
                <img
                  src={m.thumbnail}
                  alt=""
                  referrerPolicy="no-referrer"
                  style={{
                    width: "100%",
                    height: 120,
                    objectFit: "cover",
                    borderRadius: 6,
                    marginBottom: 6,
                  }}
                />
              )}
              <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 2 }}>
                {m.price ? formatPrice(m.price) : "Prezzo su richiesta"}
              </div>
              <div style={{ fontSize: 12, marginBottom: 6, lineHeight: 1.3 }}>
                {m.title}
              </div>
              <Link
                href={`/listing/${m.id}`}
                style={{ color: "#2563eb", fontSize: 12, fontWeight: 600 }}
              >
                Vedi dettagli →
              </Link>
            </div>
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}
