import { Clock } from "lucide-react";
import { cn, publishedSince } from "@/lib/utils";

const fullDate = new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "long", year: "numeric" });

interface PublishedAtProps {
  /** Portal publication date (YYYY-MM-DD). */
  date: string | null | undefined;
  /** Shown (with the clock) when the date is missing; nothing if omitted. */
  fallback?: string;
  className?: string;
  iconClassName?: string;
}

/**
 * How long ago a listing was published: a clock and "3 giorni fa". The
 * clock says what the time is about, so the word "Pubblicato" stays only
 * for screen readers and in the tooltip, next to the exact date.
 */
export function PublishedAt({ date, fallback, className, iconClassName }: PublishedAtProps) {
  const since = publishedSince(date);
  const label = since ?? fallback;
  if (!label) return null;
  const exact = since && date ? fullDate.format(new Date(`${date.slice(0, 10)}T00:00:00`)) : null;

  return (
    <span
      className={cn("inline-flex items-center gap-1 whitespace-nowrap", className)}
      title={exact ? `Pubblicato il ${exact}` : undefined}
    >
      <Clock className={cn("h-3 w-3 shrink-0", iconClassName)} aria-hidden />
      {since && <span className="sr-only">Pubblicato </span>}
      {label.charAt(0).toUpperCase() + label.slice(1)}
    </span>
  );
}
