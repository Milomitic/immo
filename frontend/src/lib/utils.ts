import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Pick the size of a portal photo for where it's shown. Portal CDNs serve
 * several sizes of each image and the scrapers store whichever the page
 * used. Measured 2026-10-13:
 *  - immobiliare: m-c 1024x768 (112 KB) → xs-c 640x480 (57 KB) for cards
 *  - casa.it: resizes to any WxH up to 800x600 → 640x480 (37 KB vs 53 KB)
 *  - tecnocasa: detail 1024x768 → gallery 1200x900 for the full view
 *  - wikicasa: stored at 1280x960 (webp) → 640x480 for cards
 *  - subito: a size "rule" in the query → the card rule for cards
 * Other portals (remax, gabetti, vistocasa) expose a single size.
 */
export function imageVariant(url: string, use: "card" | "full"): string {
  if (use === "card") {
    if (url.includes("pwm.im-cdn.it/image/")) return url.replace(/\/m-c\.jpg$/, "/xs-c.jpg");
    if (/\/\/images-\d+\.casa\.it\//.test(url)) return url.replace(/\/\d+x\d+\/listing\//, "/640x480/listing/");
    if (url.includes("images.wk-cdn.it/")) return url.replace(/\/webp\/\d+x\d+\.webp$/, "/webp/640x480.webp");
    if (url.includes("images.sbito.it/")) return url.replace(/rule=[\w-]+/, "rule=large-fixed-card-1x-auto");
  } else if (url.includes("medialabtc.it/")) {
    return url.replace(/\/detail\.jpeg$/, "/gallery.jpeg");
  }
  return url;
}

export function formatPrice(price: number | null): string {
  if (price === null) return "Prezzo su richiesta";
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(price);
}

export function formatPriceCompact(price: number | null): string {
  if (price === null) return "N/D";
  return new Intl.NumberFormat("it-IT", { maximumFractionDigits: 0 }).format(price);
}

export function formatArea(area: number | null): string {
  if (area === null) return "N/D";
  return `${Math.round(area)} m\u00B2`;
}

export function formatPricePerSqm(price: number | null): string {
  if (price === null) return "";
  return `${formatPrice(price)}/m\u00B2`;
}

export function portalLabel(portal: string): string {
  const labels: Record<string, string> = {
    immobiliare: "Immobiliare.it",
    idealista: "Idealista",
    casa: "Casa.it",
    tecnocasa: "Tecnocasa",
    remax: "RE/MAX",
    gabetti: "Gabetti",
    vistocasa: "Vistocasa",
    wikicasa: "Wikicasa",
    subito: "Subito",
  };
  return labels[portal] || portal;
}

export function portalColor(portal: string): string {
  const colors: Record<string, string> = {
    immobiliare: "bg-blue-600",
    idealista: "bg-green-600",
    casa: "bg-orange-500",
    tecnocasa: "bg-red-600",
    remax: "bg-red-500",
    gabetti: "bg-amber-600",
    vistocasa: "bg-teal-600",
    wikicasa: "bg-indigo-600",
    subito: "bg-rose-600",
  };
  return colors[portal] || "bg-gray-500";
}

export function propertyTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    apartment: "Appartamento",
    house: "Casa",
    villa: "Villa",
    loft: "Loft",
    studio: "Monolocale",
    office: "Ufficio",
    commercial: "Commerciale",
    land: "Terreno",
  };
  return labels[type] || type;
}

export function listingTypeLabel(type: string): string {
  return type === "rent" ? "Affitto" : "Vendita";
}

export function conditionLabel(condition: string | null): string {
  if (!condition) return "N/D";
  const labels: Record<string, string> = {
    nuovo: "Nuovo",
    new: "Nuovo",
    ristrutturato: "Ristrutturato",
    renovated: "Ristrutturato",
    buono: "Buono stato",
    good: "Buono stato",
    da_ristrutturare: "Da ristrutturare",
    to_renovate: "Da ristrutturare",
  };
  return labels[condition.toLowerCase()] || condition;
}

export function floorLabel(floor: string | null): string {
  if (!floor) return "";
  const lower = floor.toLowerCase();
  if (lower === "0" || lower === "t" || lower === "terra" || lower === "piano terra")
    return "Piano terra";
  if (lower === "s" || lower === "seminterrato") return "Seminterrato";
  if (lower === "r" || lower === "rialzato") return "Rialzato";
  const num = parseInt(floor);
  if (!isNaN(num)) return `${num}\u00B0 piano`;
  return floor;
}

export function energyClassColor(ec: string | null): string {
  if (!ec) return "bg-gray-100 text-gray-600";
  const cls = ec.toUpperCase();
  if (cls.startsWith("A")) return "bg-green-100 text-green-800";
  if (cls === "B") return "bg-lime-100 text-lime-800";
  if (cls === "C") return "bg-yellow-100 text-yellow-800";
  if (cls === "D") return "bg-amber-100 text-amber-800";
  if (cls === "E") return "bg-orange-100 text-orange-800";
  if (cls === "F") return "bg-red-100 text-red-700";
  if (cls === "G") return "bg-red-200 text-red-800";
  return "bg-gray-100 text-gray-600";
}

export function isNewListing(firstSeenAt: string): boolean {
  const date = new Date(firstSeenAt);
  const now = new Date();
  return now.getTime() - date.getTime() < 24 * 60 * 60 * 1000;
}

export function timeAgo(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffHours / 24);

  if (diffHours < 1) return "Adesso";
  if (diffHours < 24) return `${diffHours}h fa`;
  if (diffDays < 7) return `${diffDays}g fa`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} sett. fa`;
  return date.toLocaleDateString("it-IT");
}

/**
 * Pick the best "when was this listing posted" label.
 *
 * Prefers publication_date from the source portal. If it's missing, returns
 * `null` so the UI can show nothing rather than falsely claim the listing
 * is brand new (first_seen_at is just when *we* scraped it — useless as a
 * "posted on" signal).
 */
export function listingPostedAt(listing: {
  publication_date?: string | null;
  first_seen_at?: string;
}): string | null {
  if (listing.publication_date) return listing.publication_date;
  return null;
}

/**
 * "oggi", "ieri", "3 giorni fa", "2 settimane fa"… for a portal publication
 * date. Those are calendar dates (YYYY-MM-DD) without a time, so counting
 * hours would invent precision: compare local calendar days instead.
 */
export function publishedSince(dateStr: string | null | undefined): string | null {
  if (!dateStr) return null;
  const published = new Date(`${dateStr.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(published.getTime())) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = Math.round((today.getTime() - published.getTime()) / 86_400_000);
  if (days <= 0) return "oggi";
  if (days === 1) return "ieri";
  if (days < 7) return `${days} giorni fa`;
  if (days < 30) {
    const weeks = Math.floor(days / 7);
    return weeks === 1 ? "1 settimana fa" : `${weeks} settimane fa`;
  }
  if (days < 365) {
    const months = Math.floor(days / 30);
    return months === 1 ? "1 mese fa" : `${months} mesi fa`;
  }
  const years = Math.floor(days / 365);
  return years === 1 ? "1 anno fa" : `${years} anni fa`;
}

/**
 * Format a first_seen_at / last_seen_at timestamp. These represent when *we*
 * observed the listing, not when it was posted — always label them clearly.
 */
export function seenAgo(dateStr: string): string {
  return timeAgo(dateStr);
}

export function roomsLabel(rooms: number | null): string {
  if (!rooms) return "";
  if (rooms === 1) return "Monolocale";
  if (rooms === 2) return "Bilocale";
  if (rooms === 3) return "Trilocale";
  if (rooms === 4) return "Quadrilocale";
  return `${rooms} locali`;
}
