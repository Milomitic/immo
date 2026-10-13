"use client";

import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchLastUpdate, fetchScrapeStatus, triggerScrape } from "@/lib/api";
import type { ScrapeStatus } from "@/lib/types";

const STATUS_KEY = ["scrape-status"] as const;
const LAST_UPDATE_KEY = ["scrape-last-update"] as const;

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
 * When the catalogue was last refreshed. Re-read whenever a scan stops
 * running, so the date next to "Aggiorna annunci" moves on its own.
 */
export function useLastUpdate() {
  const qc = useQueryClient();
  const { data: status } = useScrapeStatus();
  const running = status?.is_running ?? false;
  useEffect(() => {
    if (!running) qc.invalidateQueries({ queryKey: LAST_UPDATE_KEY });
  }, [running, qc]);
  return useQuery({ queryKey: LAST_UPDATE_KEY, queryFn: fetchLastUpdate, staleTime: 60_000 });
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
    onMutate: async () => {
      await qc.cancelQueries({ queryKey: STATUS_KEY });
      const previous = qc.getQueryData<ScrapeStatus>(STATUS_KEY);
      qc.setQueryData<ScrapeStatus>(STATUS_KEY, {
        is_running: true,
        is_stale: false,
        started_at: new Date().toISOString(),
        finished_at: null,
        seconds_since_last_progress: null,
        progress_done: 0,
        progress_total: 0,
        phase: "search",
        // The previous job's runs would show up as pills in the new toast.
        runs: [],
      });
      return { previous };
    },
    onError: (_err, _vars, context) => {
      // 409 (already running), 401 (token) or a network error: put back
      // what the server last told us, then re-sync.
      if (context?.previous) qc.setQueryData(STATUS_KEY, context.previous);
      qc.invalidateQueries({ queryKey: STATUS_KEY });
    },
    onSuccess: () => {
      // Refetch quickly a few times to catch the freshly-inserted run row.
      [500, 1500, 3000].forEach((ms) =>
        setTimeout(() => qc.invalidateQueries({ queryKey: STATUS_KEY }), ms),
      );
    },
  });
}
