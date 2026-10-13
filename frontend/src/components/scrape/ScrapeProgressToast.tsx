"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronUp, Loader2, X } from "lucide-react";
import { useScrapeStatus } from "@/hooks/useScrapeStatus";
import { cn } from "@/lib/utils";
import { PortalPills } from "./PortalPills";
import { formatSecs, phaseLabel, runTotals } from "./scrapeProgress";
import { useScrapeEta } from "./useScrapeEta";
import { useToastVisibility } from "./useToastVisibility";

const BODY_ID = "scrape-toast-body";

// On a phone the toast spans the screen width, so it starts reduced to its
// header (with a thin progress bar) instead of covering the map or list.
const startsCollapsed = () =>
  typeof window !== "undefined" && window.matchMedia("(max-width: 639px)").matches;

/**
 * Persistent floating progress toast — bottom-right on desktop, full width
 * at the bottom on phones; survives route changes (mounted in RootLayout).
 * Shows live progress + ETA while a scrape is running, lingers ~30s after
 * completion with the result summary, then unmounts. It can be reduced to
 * one line at any time.
 */
export function ScrapeProgressToast() {
  const { data } = useScrapeStatus();
  const { visible, dismiss } = useToastVisibility(data);
  const { etaSecs, percent, elapsedSecs } = useScrapeEta(data);
  const [collapsed, setCollapsed] = useState(startsCollapsed);

  if (!data || !visible) return null;

  const running = data.is_running;
  const totals = runTotals(data.runs);
  const title = running ? "Aggiornamento annunci…" : "Aggiornamento completato";

  return (
    <section
      aria-label="Aggiornamento annunci"
      className={cn(
        "fixed z-[1100] inset-x-4 bottom-[max(1rem,env(safe-area-inset-bottom))]",
        "sm:inset-x-auto sm:right-5 sm:bottom-5 sm:w-[360px]",
        "rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--background)] shadow-2xl overflow-hidden",
      )}
    >
      {/* Announced only when the phase or the outcome changes, not on
          every 2s progress tick. */}
      <p role="status" className="sr-only">
        {running ? `${title} ${phaseLabel(data.phase)}` : title}
      </p>

      <div className={cn("flex items-center gap-2 px-4 py-3", !collapsed && "border-b border-[var(--border)]")}>
        {running ? (
          <Loader2 className="h-4 w-4 shrink-0 text-[var(--primary)] animate-spin" aria-hidden />
        ) : totals.errors > 0 ? (
          <AlertTriangle className="h-4 w-4 shrink-0 text-[var(--warning)]" aria-hidden />
        ) : (
          <CheckCircle2 className="h-4 w-4 shrink-0 text-[var(--success)]" aria-hidden />
        )}
        <div className="flex-1 min-w-0 truncate text-sm font-semibold" aria-hidden>
          {title}
        </div>
        {collapsed && running && data.progress_total > 0 && (
          <span className="text-xs tabular-nums text-[var(--muted-foreground)]">{percent.toFixed(0)}%</span>
        )}
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          className="p-1 rounded hover:bg-[var(--muted)] transition-colors"
          aria-expanded={!collapsed}
          aria-controls={BODY_ID}
          aria-label={collapsed ? "Mostra dettagli" : "Riduci"}
          title={collapsed ? "Mostra dettagli" : "Riduci"}
        >
          {collapsed ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </button>
        {!running && (
          <button
            type="button"
            onClick={dismiss}
            className="p-1 rounded hover:bg-[var(--muted)] transition-colors"
            aria-label="Chiudi"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {collapsed && running && <ProgressBar percent={percent} className="h-1 rounded-none" />}

      <div id={BODY_ID} hidden={collapsed} className="px-4 py-3 space-y-2">
        {data.is_stale && (
          <div className="flex items-center gap-1.5 text-xs text-[var(--warning)] bg-[var(--warning)]/10 rounded px-2 py-1">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden />
            Nessun aggiornamento da {data.seconds_since_last_progress ?? "?"}s — possibile blocco
          </div>
        )}

        <div className="flex items-center justify-between text-xs text-[var(--muted-foreground)]">
          <span>{phaseLabel(data.phase)}</span>
          {running && etaSecs != null && (
            // In search the detail workload isn't known yet: the ETA only
            // covers the search pages, and says so.
            <span>{data.phase === "search" ? "Fine ricerca" : "ETA"} ~{formatSecs(etaSecs)}</span>
          )}
          {!running && <span>{formatSecs(elapsedSecs)} totali</span>}
        </div>

        {running ? (
          <>
            <ProgressBar percent={percent} />
            <div className="flex justify-between text-[11px] text-[var(--muted-foreground)] tabular-nums">
              <span>
                {data.progress_done.toLocaleString("it-IT")} / {data.progress_total.toLocaleString("it-IT")}
                {data.phase === "search" ? " pagine" : " annunci"}
              </span>
              <span>{percent.toFixed(0)}%</span>
            </div>
          </>
        ) : (
          <div className="text-xs text-[var(--muted-foreground)]">
            <span className="font-semibold text-[var(--foreground)]">{totals.seen.toLocaleString("it-IT")}</span> verificati
            {" · "}
            <span className="font-semibold text-[var(--foreground)]">{totals.newCount.toLocaleString("it-IT")}</span> nuovi
            {totals.errors > 0 && (
              <>
                {" · "}
                <span className="text-[var(--destructive)]">
                  {totals.errors} {totals.errors === 1 ? "errore" : "errori"}
                </span>
              </>
            )}
          </div>
        )}

        <PortalPills runs={data.runs} />
      </div>
    </section>
  );
}

function ProgressBar({ percent, className }: { percent: number; className?: string }) {
  return (
    <div className={cn("h-1.5 rounded-full bg-[var(--muted)] overflow-hidden", className)}>
      <div
        className="h-full bg-[var(--primary)] transition-all duration-500 ease-out"
        style={{ width: `${percent}%` }}
      />
    </div>
  );
}
