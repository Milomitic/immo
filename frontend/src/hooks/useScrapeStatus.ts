"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchScrapeStatus, triggerScrape } from "@/lib/api";
import type { ScrapeStatus } from "@/lib/types";

const STATUS_KEY = ["scrape-status"] as const;

/**
 * Poll the aggregated scrape status. Refetches every 2 seconds while
 * a scrape is running, every 30 seconds when idle — keeps the UI
 * responsive during a job without hammering the API the rest of the
 * time.
 */
export function useScrapeStatus() {
  return useQuery<ScrapeStatus>({
    queryKey: STATUS_KEY,
    queryFn: fetchScrapeStatus,
    refetchInterval: (query) => {
      const data = query.state.data as ScrapeStatus | undefined;
      return data?.is_running ? 2_000 : 30_000;
    },
    // Keep showing the previous response while the next one is in
    // flight — avoids the progress bar flickering to "0/0" between polls.
    placeholderData: (prev) => prev,
  });
}

/**
 * Trigger a scrape with an optimistic UI bump so the toast appears
 * immediately. Without this nudge the user would click the button
 * and watch nothing happen for 2 seconds (until the first poll comes
 * back with ``is_running: true``).
 */
export function useTriggerScrape() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ portal = "all", city }: { portal?: string; city?: string }) =>
      triggerScrape(portal, city),
    onMutate: () => {
      qc.setQueryData<ScrapeStatus>(STATUS_KEY, (prev) => ({
        ...(prev ?? {
          is_running: false,
          is_stale: false,
          started_at: null,
          finished_at: null,
          seconds_since_last_progress: null,
          progress_done: 0,
          progress_total: 0,
          phase: "search",
          runs: [],
        }),
        is_running: true,
        is_stale: false,
        phase: "search",
        started_at: new Date().toISOString(),
        finished_at: null,
      }));
    },
    onSuccess: () => {
      // Refetch quickly a few times to catch the freshly-inserted run row.
      [500, 1500, 3000].forEach((ms) =>
        setTimeout(() => qc.invalidateQueries({ queryKey: STATUS_KEY }), ms),
      );
    },
  });
}
