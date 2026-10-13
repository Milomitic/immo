"use client";

import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, AlertTriangle, Loader2, X } from "lucide-react";
import { useScrapeStatus } from "@/hooks/useScrapeStatus";
import { portalLabel } from "@/lib/utils";

const POST_COMPLETION_VISIBLE_MS = 30_000;

function formatSecs(s: number): string {
  if (!Number.isFinite(s) || s <= 0) return "—";
  const m = Math.floor(s / 60);
  const r = Math.round(s - m * 60);
  if (m <= 0) return `${r}s`;
  return `${m}m ${r}s`;
}

/**
 * Persistent floating progress toast — bottom-right, survives route
 * changes (mounted in RootLayout). Shows live progress + ETA while a
 * scrape is running, lingers ~30s after completion with the result
 * summary, then unmounts.
 */
export function ScrapeProgressToast() {
  const { data } = useScrapeStatus();
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

  // Auto-dismiss 30s after completion.
  useEffect(() => {
    if (completedAt == null) return;
    const t = setTimeout(() => setDismissed(true), POST_COMPLETION_VISIBLE_MS);
    return () => clearTimeout(t);
  }, [completedAt]);

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

  // ETA — observed in-phase rate once we have 3s and 1 item of it,
  // baseline otherwise.
  const { etaSecs, percent, elapsedSecs } = useMemo(() => {
    if (!data || !data.started_at) return { etaSecs: null as number | null, percent: 0, elapsedSecs: 0 };
    const elapsed = Math.max(0, (Date.now() - new Date(data.started_at).getTime()) / 1000);
    const done = data.progress_done;
    const total = data.progress_total;
    let pct = 0;
    if (total > 0) pct = Math.min(100, (done / total) * 100);
    let eta: number | null = null;
    if (total > 0) {
      const phaseSecs = phaseMark ? (Date.now() - phaseMark.at) / 1000 : 0;
      const phaseDone = phaseMark ? done - phaseMark.done : 0;
      if (phaseDone >= 1 && phaseSecs >= 3) {
        eta = (total - done) / (phaseDone / phaseSecs);
      } else {
        // Baseline: the per-portal rate limit is ~1 request/s, and every
        // remaining unit (search page or listing) costs one request.
        eta = total - done;
      }
    }
    return { etaSecs: eta, percent: pct, elapsedSecs: elapsed };
  }, [data, phaseMark]);

  if (!data) return null;

  const inPostWindow = completedAt != null && !data.is_running;
  const visible = (data.is_running || inPostWindow) && !dismissed && data.runs.length > 0;
  if (!visible) return null;

  // Aggregate counters across runs for the post-completion summary.
  const totalsNew = data.runs.reduce((a, r) => a + (r.listings_new ?? 0), 0);
  // "Seen" = every listing checked on the search pages. With immutable
  // snapshots most are known, so "new" alone undersells what a scan did.
  const totalsSeen = data.runs.reduce((a, r) => a + (r.listings_seen ?? r.listings_found ?? 0), 0);
  const totalsErrors = data.runs.reduce((a, r) => a + (r.errors ?? 0), 0);

  const phaseLabel = data.phase === "search"
    ? "Ricerca annunci"
    : data.phase === "fetch"
    ? "Elaborazione dettagli"
    : data.phase === "done"
    ? "Completato"
    : data.phase === "failed"
    ? "Errore"
    : "In coda";

  // Per-portal mini-progress so the user sees which spider is the
  // bottleneck without opening logs.
  const activeRuns = data.runs.filter((r) => r.status === "running");
  const finishedRuns = data.runs.filter((r) => r.status !== "running");

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-5 right-5 z-[1100] w-[360px] max-w-[calc(100vw-2rem)] rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--background)] shadow-2xl overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[var(--border)]">
        {data.is_running ? (
          <Loader2 className="h-4 w-4 text-[var(--primary)] animate-spin" />
        ) : totalsErrors > 0 ? (
          <AlertTriangle className="h-4 w-4 text-[var(--warning)]" />
        ) : (
          <CheckCircle2 className="h-4 w-4 text-[var(--success)]" />
        )}
        <div className="flex-1 text-sm font-semibold">
          {data.is_running ? "Aggiornamento annunci…" : "Aggiornamento completato"}
        </div>
        {!data.is_running && (
          <button
            onClick={() => setDismissed(true)}
            className="p-1 rounded hover:bg-[var(--muted)] transition-colors"
            aria-label="Chiudi"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Body */}
      <div className="px-4 py-3 space-y-2">
        {/* Stale warning */}
        {data.is_stale && (
          <div className="flex items-center gap-1.5 text-xs text-[var(--warning)] bg-[var(--warning)]/10 rounded px-2 py-1">
            <AlertTriangle className="h-3.5 w-3.5" />
            Nessun aggiornamento da {data.seconds_since_last_progress ?? "?"}s — possibile blocco
          </div>
        )}

        {/* Phase + ETA row */}
        <div className="flex items-center justify-between text-xs text-[var(--muted-foreground)]">
          <span>{phaseLabel}</span>
          {data.is_running && etaSecs != null && (
            // In search the detail workload isn't known yet: the ETA only
            // covers the search pages, and says so.
            <span>{data.phase === "search" ? "Fine ricerca" : "ETA"} ~{formatSecs(etaSecs)}</span>
          )}
          {!data.is_running && (
            <span>{formatSecs(elapsedSecs)} totali</span>
          )}
        </div>

        {/* Progress bar */}
        {data.is_running && (
          <>
            <div className="h-1.5 rounded-full bg-[var(--muted)] overflow-hidden">
              <div
                className="h-full bg-[var(--primary)] transition-all duration-500 ease-out"
                style={{ width: `${percent}%` }}
              />
            </div>
            <div className="flex justify-between text-[11px] text-[var(--muted-foreground)] tabular-nums">
              <span>
                {data.progress_done.toLocaleString("it-IT")} / {data.progress_total.toLocaleString("it-IT")}
                {data.phase === "search" ? " pagine" : " annunci"}
              </span>
              <span>{percent.toFixed(0)}%</span>
            </div>
          </>
        )}

        {/* Summary on completion */}
        {!data.is_running && (
          <div className="text-xs text-[var(--muted-foreground)] space-y-1">
            <div>
              <span className="font-semibold text-[var(--foreground)]">{totalsSeen.toLocaleString("it-IT")}</span> verificati
              {" · "}
              <span className="font-semibold text-[var(--foreground)]">{totalsNew.toLocaleString("it-IT")}</span> nuovi
              {totalsErrors > 0 && (
                <>
                  {" · "}
                  <span className="text-[var(--destructive)]">{totalsErrors} errori</span>
                </>
              )}
            </div>
          </div>
        )}

        {/* Per-portal pills */}
        {activeRuns.length > 0 && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {activeRuns.map((r) => {
              const d = r.progress_done ?? 0;
              const t = r.progress_total ?? 0;
              return (
                <span
                  key={r.id}
                  className="inline-flex items-center gap-1 rounded-full bg-[var(--primary)]/10 text-[var(--primary)] text-[10px] font-medium px-2 py-0.5"
                  title={`${portalLabel(r.portal)}: ${d}/${t}`}
                >
                  <Loader2 className="h-2.5 w-2.5 animate-spin" />
                  {portalLabel(r.portal)} {t > 0 ? `${Math.round((d / t) * 100)}%` : "…"}
                </span>
              );
            })}
          </div>
        )}
        {activeRuns.length === 0 && finishedRuns.length > 0 && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {finishedRuns.map((r) => (
              <span
                key={r.id}
                className={`inline-flex items-center gap-1 rounded-full text-[10px] font-medium px-2 py-0.5 ${
                  r.errors > 0
                    ? "bg-[var(--warning)]/10 text-[var(--warning)]"
                    : "bg-[var(--success)]/10 text-[var(--success)]"
                }`}
                title={
                  `${portalLabel(r.portal)}: ${r.listings_seen ?? 0} verificati, ${r.listings_new} nuovi` +
                  (r.coverage_complete === false ? " — catalogo visto solo in parte" : "")
                }
              >
                {r.errors > 0 ? "⚠" : "✓"} {portalLabel(r.portal)}
                {r.coverage_complete === false && <span className="opacity-70">(parziale)</span>}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
