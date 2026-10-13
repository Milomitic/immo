import { Loader2 } from "lucide-react";
import type { ScrapeRun } from "@/lib/types";
import { cn, portalLabel } from "@/lib/utils";

const PILL = "inline-flex items-center gap-1 rounded-full text-[10px] font-medium px-2 py-0.5";

/**
 * One pill per portal: live percentage while the job runs (shows which
 * spider is the bottleneck without opening logs), outcome once it's done.
 */
export function PortalPills({ runs }: { runs: ScrapeRun[] }) {
  const active = runs.filter((r) => r.status === "running");
  const shown = active.length > 0 ? active : runs;
  if (shown.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1.5 pt-1">
      {shown.map((r) => (r.status === "running" ? <RunningPill key={r.id} run={r} /> : <FinishedPill key={r.id} run={r} />))}
    </div>
  );
}

function RunningPill({ run }: { run: ScrapeRun }) {
  const done = run.progress_done ?? 0;
  const total = run.progress_total ?? 0;
  return (
    <span
      className={cn(PILL, "bg-[var(--primary)]/10 text-[var(--primary)]")}
      title={`${portalLabel(run.portal)}: ${done}/${total}`}
    >
      <Loader2 className="h-2.5 w-2.5 animate-spin" aria-hidden />
      {portalLabel(run.portal)} {total > 0 ? `${Math.round((done / total) * 100)}%` : "…"}
    </span>
  );
}

function FinishedPill({ run }: { run: ScrapeRun }) {
  const failed = run.errors > 0;
  return (
    <span
      className={cn(
        PILL,
        failed ? "bg-[var(--warning)]/10 text-[var(--warning)]" : "bg-[var(--success)]/10 text-[var(--success)]",
      )}
      title={
        `${portalLabel(run.portal)}: ${run.listings_seen ?? 0} verificati, ${run.listings_new} nuovi` +
        (run.coverage_complete === false ? " — catalogo visto solo in parte" : "")
      }
    >
      {failed ? "⚠" : "✓"} {portalLabel(run.portal)}
      {run.coverage_complete === false && <span className="opacity-70">(parziale)</span>}
    </span>
  );
}
