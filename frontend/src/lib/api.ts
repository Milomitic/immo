import type {
  Favorite,
  ListingDetail,
  ListingMarkersResponse,
  ListingSearchParams,
  PaginatedListings,
  PricePoint,
  ScrapeStatus,
  ScrapeTriggerResponse,
  Stats,
  Listing,
} from "./types";

const API_ROOT = `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/v1`;

// Optional guard token for mutating endpoints (backend ADMIN_TOKEN). It ends
// up in the browser bundle, so it only keeps strangers out of a LAN/tunnel
// deployment — it is not user authentication.
const ADMIN_TOKEN = process.env.NEXT_PUBLIC_ADMIN_TOKEN;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function fetchApi<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { ...(init?.headers as Record<string, string>) };
  // Only send Content-Type with a body: on a GET it makes the request
  // "non-simple" and costs a CORS preflight round-trip every time.
  if (init?.body) headers["Content-Type"] = "application/json";
  if (ADMIN_TOKEN && init?.method && init.method !== "GET") headers["X-Admin-Token"] = ADMIN_TOKEN;

  const res = await fetch(`${API_ROOT}${path}`, { ...init, headers });
  if (res.status === 204) return undefined as T;
  if (!res.ok) {
    let detail = `Errore API ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // non-JSON error body: keep the generic message
    }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

function toQuery(params: object): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") qs.set(key, String(value));
  }
  return qs.toString();
}

export async function fetchListings(params: ListingSearchParams): Promise<PaginatedListings> {
  return fetchApi<PaginatedListings>(`/listings?${toQuery(params)}`);
}

export async function fetchMapMarkers(
  params: ListingSearchParams & { limit?: number },
): Promise<ListingMarkersResponse> {
  return fetchApi<ListingMarkersResponse>(`/listings/map?${toQuery(params)}`);
}

export async function fetchListing(id: string): Promise<ListingDetail> {
  return fetchApi<ListingDetail>(`/listings/${id}`);
}

export async function fetchSimilarListings(id: string): Promise<Listing[]> {
  return fetchApi<Listing[]>(`/listings/${id}/similar`);
}

export async function fetchPriceHistory(id: string): Promise<PricePoint[]> {
  return fetchApi<PricePoint[]>(`/listings/${id}/price-history`);
}

export async function fetchFavorites(): Promise<Favorite[]> {
  return fetchApi<Favorite[]>(`/favorites`);
}

export async function fetchFavoriteIds(): Promise<string[]> {
  return fetchApi<string[]>(`/favorites/ids`);
}

export async function saveFavorite(listingId: string): Promise<Favorite> {
  return fetchApi<Favorite>(`/favorites/${listingId}`, { method: "PUT" });
}

export async function removeFavorite(listingId: string): Promise<void> {
  return fetchApi<void>(`/favorites/${listingId}`, { method: "DELETE" });
}

export async function fetchStats(): Promise<Stats> {
  return fetchApi<Stats>(`/stats`);
}

export async function triggerScrape(portal: string = "all", city?: string): Promise<ScrapeTriggerResponse> {
  return fetchApi<ScrapeTriggerResponse>(`/scrape/trigger`, {
    method: "POST",
    body: JSON.stringify({ portal, ...(city ? { city } : {}) }),
  });
}

export async function fetchScrapeStatus(): Promise<ScrapeStatus> {
  return fetchApi<ScrapeStatus>(`/scrape/status`);
}
