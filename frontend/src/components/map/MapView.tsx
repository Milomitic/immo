"use client";

import { useEffect } from "react";
import { MapContainer, TileLayer, Marker, Popup, useMapEvents } from "react-leaflet";
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

function ViewportSync({ onChange }: ViewportSyncProps) {
  const map = useMapEvents({
    moveend: () => emitBbox(map, onChange),
  });

  useEffect(() => {
    // Leaflet needs a frame to lay out the container at full size.
    // Without invalidateSize + raf, getBounds() returns a zero-area point.
    const raf = requestAnimationFrame(() => {
      map.invalidateSize();
      emitBbox(map, onChange);
    });
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return null;
}

interface MapViewProps {
  markers: ListingMarker[];
  center: [number, number];
  zoom: number;
  onViewportChange: (bbox: string) => void;
  selectedId?: string | null;
  onMarkerClick?: (id: string) => void;
}

export default function MapView({
  markers,
  center,
  zoom,
  onViewportChange,
  selectedId,
  onMarkerClick,
}: MapViewProps) {
  return (
    <MapContainer
      center={center}
      zoom={zoom}
      scrollWheelZoom
      style={{ width: "100%", height: "100%" }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <ViewportSync onChange={onViewportChange} />
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
