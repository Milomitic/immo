"use client";

import { useEffect, useMemo, useState } from "react";
import type { ScrapeStatus } from "@/lib/types";

/**
 * Progress percentage, ETA and elapsed time of the running job.
 *
 * The ETA uses the rate observed within the current phase once there are
 * 3s and 1 item of it, and a baseline before that.
 */
export function useScrapeEta(data: ScrapeStatus | undefined) {
  // Where the current phase stood when this client first saw it. Progress
  // restarts per phase (search pages, then listings), so the rate must be
  // measured within the phase: job-wide elapsed time includes the search
  // phase and made the detail ETA far too pessimistic.
  const [phaseMark, setPhaseMark] = useState<{ phase: string | null; at: number; done: number } | null>(null);
  useEffect(() => {
    if (!data?.is_running) {
      setPhaseMark(null);
      return;
    }
    setPhaseMark((prev) =>
      prev && prev.phase === data.phase && data.progress_done >= prev.done
        ? prev
        : { phase: data.phase, at: Date.now(), done: data.progress_done },
    );
  }, [data]);

  return useMemo(() => {
    if (!data || !data.started_at) return { etaSecs: null as number | null, percent: 0, elapsedSecs: 0 };
    const elapsed = Math.max(0, (Date.now() - new Date(data.started_at).getTime()) / 1000);
    const done = data.progress_done;
    const total = data.progress_total;
    if (total <= 0) return { etaSecs: null, percent: 0, elapsedSecs: elapsed };

    const percent = Math.min(100, (done / total) * 100);
    const phaseSecs = phaseMark ? (Date.now() - phaseMark.at) / 1000 : 0;
    const phaseDone = phaseMark ? done - phaseMark.done : 0;
    const etaSecs =
      phaseDone >= 1 && phaseSecs >= 3
        ? (total - done) / (phaseDone / phaseSecs)
        : // Baseline: the per-portal rate limit is ~1 request/s, and every
          // remaining unit (search page or listing) costs one request.
          total - done;
    return { etaSecs, percent, elapsedSecs: elapsed };
  }, [data, phaseMark]);
}
