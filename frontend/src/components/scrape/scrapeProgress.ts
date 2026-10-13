import type { ScrapeRun } from "@/lib/types";

/** "1m 5s"-style duration, "—" when unknown. */
export function formatSecs(s: number): string {
  if (!Number.isFinite(s) || s <= 0) return "—";
  const m = Math.floor(s / 60);
  const r = Math.round(s - m * 60);
  if (m <= 0) return `${r}s`;
  return `${m}m ${r}s`;
}

export function phaseLabel(phase: string | null): string {
  switch (phase) {
    case "search":
      return "Ricerca annunci";
    case "fetch":
      return "Elaborazione dettagli";
    case "done":
      return "Completato";
    case "failed":
      return "Errore";
    default:
      return "In coda";
  }
}

/** What a job did, summed across its per-portal runs. */
export function runTotals(runs: ScrapeRun[]) {
  return {
    newCount: runs.reduce((a, r) => a + (r.listings_new ?? 0), 0),
    // "Seen" = every listing checked on the search pages. With immutable
    // snapshots most are known, so "new" alone undersells what a scan did.
    seen: runs.reduce((a, r) => a + (r.listings_seen ?? r.listings_found ?? 0), 0),
    errors: runs.reduce((a, r) => a + (r.errors ?? 0), 0),
  };
}
