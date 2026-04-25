import type { ListingDetail, ListingMarkersResponse, ListingSearchParams, PaginatedListings, Stats, Listing } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function fetchApi<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!res.ok) {
    throw new ApiError(res.status, `API error: ${res.status}`);
  }

  return res.json();
}

export async function fetchListings(params: ListingSearchParams): Promise<PaginatedListings> {
  const searchParams = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      searchParams.set(key, String(value));
    }
  }

  return fetchApi<PaginatedListings>(`/api/listings?${searchParams}`);
}

export async function fetchMapMarkers(
  params: ListingSearchParams & { limit?: number },
): Promise<ListingMarkersResponse> {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      searchParams.set(key, String(value));
    }
  }
  return fetchApi<ListingMarkersResponse>(`/api/listings/map?${searchParams}`);
}

export async function fetchListing(id: string): Promise<ListingDetail> {
  return fetchApi<ListingDetail>(`/api/listings/${id}`);
}

export async function fetchSimilarListings(id: string): Promise<Listing[]> {
  return fetchApi<Listing[]>(`/api/listings/${id}/similar`);
}

export async function fetchStats(): Promise<Stats> {
  return fetchApi<Stats>(`/api/stats`);
}

export async function triggerScrape(portal: string = "all") {
  return fetchApi(`/api/scrape/trigger`, {
    method: "POST",
    body: JSON.stringify({ portal }),
  });
}
