"use client";

import { useEffect, useState } from "react";
import type { ScrapeStatus } from "@/lib/types";

const POST_COMPLETION_VISIBLE_MS = 30_000;

/**
 * Whether the toast shows: during a job, and for 30s after it ends (with
 * the result summary) unless the user closes it. A new job brings it back.
 */
export function useToastVisibility(data: ScrapeStatus | undefined) {
  const [dismissed, setDismissed] = useState(false);
  const [completedAt, setCompletedAt] = useState<number | null>(null);

  // Track when the run transitions from running → not running. Open the
  // post-completion window so the user sees the final stats briefly.
  useEffect(() => {
    if (!data) return;
    if (!data.is_running && data.runs.length > 0 && completedAt == null) {
      const anyHadProgress = data.runs.some((r) => (r.progress_done ?? 0) > 0 || r.listings_found > 0);
      if (anyHadProgress) setCompletedAt(Date.now());
    }
    if (data.is_running) {
      // New run kicked off — reset both flags so the toast re-appears.
      setCompletedAt(null);
      setDismissed(false);
    }
  }, [data, completedAt]);

  useEffect(() => {
    if (completedAt == null) return;
    const t = setTimeout(() => setDismissed(true), POST_COMPLETION_VISIBLE_MS);
    return () => clearTimeout(t);
  }, [completedAt]);

  const inPostWindow = completedAt != null && !data?.is_running;
  const visible = !!data && (data.is_running || inPostWindow) && !dismissed && data.runs.length > 0;
  return { visible, dismiss: () => setDismissed(true) };
}
