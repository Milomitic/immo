"use client";

import { History } from "lucide-react";
import { usePriceHistory } from "@/hooks/useListings";
import { formatPrice } from "@/lib/utils";
import type { PricePoint } from "@/lib/types";

// Chart coordinate space; the SVG stretches it to the card width.
const W = 300;
const H = 64;
const MAX_ROWS = 5;

const dateFormat = new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "short", year: "numeric" });
const fmtDate = (iso: string) => dateFormat.format(new Date(iso));

function pct(from: number, to: number): string {
  const value = ((to - from) / from) * 100;
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

const trendClass = (delta: number) =>
  delta < 0 ? "text-[var(--positive)]" : delta > 0 ? "text-[var(--negative)]" : "text-[var(--muted-foreground)]";

/** Step line: a price holds until the next observation, then jumps; the
 *  last one holds until today. */
function stepPaths(points: PricePoint[], now: number): { line: string; area: string } {
  const times = points.map((p) => Date.parse(p.observed_at));
  const prices = points.map((p) => p.price);
  const start = times[0];
  const latest = Math.max(now, times[times.length - 1]);
  // 8% headroom on the right: a change made today still shows as a segment
  // instead of a jump flush against the edge.
  const end = latest + (latest - start) * 0.08;
  const lo = Math.min(...prices);
  const hi = Math.max(...prices);
  const pad = (hi - lo) * 0.2 || hi * 0.05 || 1;
  const x = (t: number) => (((t - start) / (end - start || 1)) * W).toFixed(1);
  const y = (p: number) => (H - ((p - lo + pad) / (hi - lo + 2 * pad)) * H).toFixed(1);

  let line = `M0,${y(prices[0])}`;
  for (let i = 1; i < points.length; i++) line += ` H${x(times[i])} V${y(prices[i])}`;
  line += ` H${W}`;
  return { line, area: `${line} V${H} H0 Z` };
}

export function PriceHistory({ listingId, listingType }: { listingId: string; listingType: string }) {
  const { data } = usePriceHistory(listingId);
  if (!data || data.length === 0) return null;

  const suffix = listingType === "rent" ? "/mese" : "";
  const first = data[0];

  if (data.length === 1) {
    return (
      <p className="flex items-center gap-1.5 text-xs text-[var(--muted-foreground)]">
        <History className="h-3.5 w-3.5" />
        Prezzo invariato dalla prima rilevazione, il {fmtDate(first.observed_at)}
      </p>
    );
  }

  const last = data[data.length - 1];
  const { line, area } = stepPaths(data, Date.now());
  // Newest change first; the first observation closes the list.
  const changes = data
    .slice(1)
    .map((point, i) => ({ point, previous: data[i].price }))
    .reverse()
    .slice(0, MAX_ROWS);

  return (
    <section className="rounded-[var(--radius-md)] border border-[var(--border)] p-4">
      <div className="flex items-baseline justify-between gap-3 mb-2">
        <h2 className="text-base font-bold flex items-center gap-1.5">
          <History className="h-4 w-4 text-[var(--primary)]" />
          Andamento prezzo
        </h2>
        <span className={`text-sm font-semibold ${trendClass(last.price - first.price)}`}>
          {pct(first.price, last.price)} dal {fmtDate(first.observed_at)}
        </span>
      </div>

      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className="w-full h-16"
        role="img"
        aria-label={`Prezzo passato da ${formatPrice(first.price)} a ${formatPrice(last.price)}`}
      >
        <path d={area} fill="var(--primary)" opacity={0.08} />
        <path
          d={line}
          fill="none"
          stroke="var(--primary)"
          strokeWidth={2}
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
      </svg>

      <ul className="mt-3 space-y-1.5 text-sm">
        {changes.map(({ point, previous }) => (
          <li key={`${point.observed_at}-${point.price}`} className="flex items-center justify-between gap-3">
            <span className="text-[var(--muted-foreground)]">{fmtDate(point.observed_at)}</span>
            <span className="flex items-center gap-2 tabular-nums">
              <span className="font-semibold">{formatPrice(point.price)}{suffix}</span>
              <span className={`text-xs font-medium ${trendClass(point.price - previous)}`}>
                {pct(previous, point.price)}
              </span>
            </span>
          </li>
        ))}
        <li className="flex items-center justify-between gap-3 text-[var(--muted-foreground)]">
          <span>{fmtDate(first.observed_at)}</span>
          <span className="tabular-nums">
            {formatPrice(first.price)}{suffix} <span className="text-xs">· prima rilevazione</span>
          </span>
        </li>
      </ul>
    </section>
  );
}
