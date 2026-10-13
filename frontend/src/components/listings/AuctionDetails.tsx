import { CalendarClock, ExternalLink, FileText, Gavel } from "lucide-react";
import type { AuctionInfo } from "@/lib/types";
import { cn, formatPrice } from "@/lib/utils";

const DATE_TIME = new Intl.DateTimeFormat("it-IT", {
  day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit",
});
const DATE_SHORT = new Intl.DateTimeFormat("it-IT", {
  day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
});

/** Auction times are local wall-clock values ("2027-01-22T16:30"): parsed
 *  without an offset, the browser reads them as local time — as published. */
function parseLocal(value: string | null | undefined): Date | null {
  if (!value) return null;
  const d = new Date(value.length === 10 ? `${value}T00:00` : value);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "tra 94 giorni" / "domani" / "oggi" / "conclusa" */
function countdown(date: Date): string {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const day = new Date(date);
  day.setHours(0, 0, 0, 0);
  const days = Math.round((day.getTime() - today.getTime()) / 86_400_000);
  if (days < 0) return "conclusa";
  if (days === 0) return "oggi";
  if (days === 1) return "domani";
  return `tra ${days} giorni`;
}

const sentenceCase = (s: string) => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();

/** The sale's data of a judicial auction, as the portal publishes it. */
export function AuctionDetails({ auction }: { auction: AuctionInfo }) {
  const date = parseLocal(auction.date);
  const deadline = parseLocal(auction.offer_deadline);
  const rows: [string, string | null][] = [
    ["Data dell'asta", date ? DATE_TIME.format(date) : null],
    ["Prezzo base", auction.base_price ? formatPrice(auction.base_price) : null],
    ["Offerta minima", auction.minimum_offer ? formatPrice(auction.minimum_offer) : null],
    ["Rilancio minimo", auction.minimum_raise ? formatPrice(auction.minimum_raise) : null],
    ["Termine per le offerte", deadline ? DATE_TIME.format(deadline) : null],
    ["Modalità", auction.sale_mode],
    ["Tribunale", auction.court],
    [
      "Procedura",
      [auction.procedure, auction.procedure_type && sentenceCase(auction.procedure_type)]
        .filter(Boolean).join(" · ") || null,
    ],
  ];

  return (
    <section
      aria-labelledby="auction-heading"
      className="rounded-[var(--radius-lg)] border border-[var(--attention)]/40 bg-[var(--attention-bg)] p-4 sm:p-5"
    >
      <h2 id="auction-heading" className="flex flex-wrap items-center gap-2 text-base font-bold text-[var(--attention)]">
        <Gavel className="h-4 w-4" aria-hidden />
        Asta giudiziaria
        {date && (
          <span className="rounded-full bg-[var(--background)] px-2 py-0.5 text-xs font-semibold">
            {countdown(date)}
          </span>
        )}
      </h2>

      <dl className="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
        {rows.filter(([, v]) => v).map(([label, value]) => (
          <div key={label} className="flex justify-between gap-3 border-b border-[var(--attention)]/15 pb-1.5">
            <dt className="text-[var(--muted-foreground)]">{label}</dt>
            <dd className="text-right font-medium">{value}</dd>
          </div>
        ))}
      </dl>

      {(auction.pvp_url || auction.documents.length > 0) && (
        <div className="mt-3 flex flex-wrap gap-2">
          {auction.pvp_url && (
            <a
              href={auction.pvp_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] bg-[var(--background)] px-3 py-1.5 text-xs font-semibold hover:underline"
            >
              <ExternalLink className="h-3.5 w-3.5" aria-hidden />
              Prenota una visita sul Portale Vendite Pubbliche
            </a>
          )}
          {auction.documents.map((doc) => (
            <a
              key={doc.url}
              href={doc.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] bg-[var(--background)] px-3 py-1.5 text-xs hover:underline"
            >
              <FileText className="h-3.5 w-3.5" aria-hidden />
              {doc.name}
            </a>
          ))}
        </div>
      )}

      <p className="mt-3 text-[11px] text-[var(--muted-foreground)]">
        Dati della vendita come pubblicati dal portale: prima di offrire leggi l&apos;avviso di vendita e la perizia.
      </p>
    </section>
  );
}

/** One line for compact places (the map's quick look). */
export function AuctionSummary({ auction, className }: { auction: AuctionInfo; className?: string }) {
  const date = parseLocal(auction.date);
  if (!date && !auction.minimum_offer) return null;
  return (
    <p className={cn("flex items-center gap-1.5 text-xs font-medium text-[var(--attention)]", className)}>
      <CalendarClock className="h-3.5 w-3.5 shrink-0" aria-hidden />
      {date && <span>Asta il {DATE_SHORT.format(date)}</span>}
      {auction.minimum_offer ? <span>· offerta minima {formatPrice(auction.minimum_offer)}</span> : null}
    </p>
  );
}
