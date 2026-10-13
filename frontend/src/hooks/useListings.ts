"use client";

import { useQuery } from "@tanstack/react-query";
import {
  fetchListing,
  fetchListings,
  fetchMapMarkers,
  fetchPriceHistory,
  fetchSimilarListings,
  fetchStats,
} from "@/lib/api";
import type { ListingSearchParams } from "@/lib/types";

export function useListings(params: ListingSearchParams) {
  return useQuery({
    queryKey: ["listings", params],
    queryFn: () => fetchListings(params),
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });
}

export function useMapMarkers(params: ListingSearchParams & { limit?: number }) {
  return useQuery({
    queryKey: ["map-markers", params],
    queryFn: () => fetchMapMarkers(params),
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  });
}

export function useListingDetail(id: string) {
  return useQuery({
    queryKey: ["listing", id],
    queryFn: () => fetchListing(id),
    enabled: !!id,
  });
}

export function useSimilarListings(id: string) {
  return useQuery({
    queryKey: ["similar", id],
    queryFn: () => fetchSimilarListings(id),
    enabled: !!id,
  });
}

export function usePriceHistory(id: string) {
  return useQuery({
    queryKey: ["price-history", id],
    queryFn: () => fetchPriceHistory(id),
    enabled: !!id,
    staleTime: 300_000,
  });
}

export function useStats() {
  return useQuery({
    queryKey: ["stats"],
    queryFn: fetchStats,
    staleTime: 300_000,
  });
}
