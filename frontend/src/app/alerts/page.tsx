"use client";

import Link from "next/link";
import { Bell, BellOff, CheckCheck, Search, Sparkles, Trash2, TrendingDown } from "lucide-react";
import { useAlerts, useDeleteAlert, useMarkAlertSeen, useUpdateAlert } from "@/hooks/useAlerts";
import { toQueryString } from "@/lib/filterParams";
import { formatPriceCompact, portalLabel, propertyTypeLabel } from "@/lib/utils";
import type { SearchAlert } from "@/lib/types";

const dateFormat = new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

const FEATURES: Record<string, string> = {
  has_elevator: "Ascensore",
  has_balcony: "Balcone",
  has_terrace: "Terrazzo",
  has_garage: "Garage",
  has_garden: "Giardino",
};

/** Short human labels for a saved search's filters. */
function describe(f: Record<string, string>): string[] {
  const out: string[] = [];
  if (f.listing_type) out.push(f.listing_type === "rent" ? "Affitto" : "Vendita");
  if (f.city) out.push(f.city.charAt(0).toUpperCase() + f.city.slice(1));
  if (f.zone) out.push(`Zona: ${f.zone}`);
  if (f.property_type) out.push(propertyTypeLabel(f.property_type));
  if (f.price_min || f.price_max) {
    const lo = f.price_min ? `€${formatPriceCompact(Number(f.price_min))}` : "";
    const hi = f.price_max ? `€${formatPriceCompact(Number(f.price_max))}` : "";
    out.push(lo && hi ? `${lo} – ${hi}` : lo ? `da ${lo}` : `fino a ${hi}`);
  }
  if (f.area_min || f.area_max) out.push(`${f.area_min ?? "0"}–${f.area_max ?? "∞"} m²`);
  if (f.rooms_min) out.push(`${f.rooms_min}+ locali`);
  if (f.bathrooms_min) out.push(`${f.bathrooms_min}+ bagni`);
  if (f.energy_class) out.push(`Classe ${f.energy_class}`);
  for (const [key, label] of Object.entries(FEATURES)) if (f[key] === "true") out.push(label);
  if (f.source_portal) out.push(`Fonte: ${portalLabel(f.source_portal)}`);
  if (f.published_within_days) out.push(`Pubblicati negli ultimi ${f.published_within_days} giorni`);
  if (f.published_after) out.push(`Pubblicati dal ${f.published_after}`);
  if (f.is_auction) out.push(f.is_auction === "true" ? "Solo aste" : "Senza aste");
  if (f.polygon) out.push("Area disegnata");
  if (f.q) out.push(`"${f.q}"`);
  return out.length ? out : ["Tutti gli annunci"];
}

function AlertCard({ alert }: { alert: SearchAlert }) {
  const markSeen = useMarkAlertSeen();
  const update = useUpdateAlert();
  const remove = useDeleteAlert();
  const since = alert.seen_at ?? alert.created_at;
  const base = alert.filters;
  const hasNews = alert.new_count + alert.price_drop_count > 0;

  return (
    <li className="rounded-[var(--radius-lg)] border border-[var(--border)] p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-semibold truncate">{alert.name}</h2>
          <p className="text-xs text-[var(--muted-foreground)]">Novità dal {dateFormat.format(new Date(since))}</p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            onClick={() => update.mutate({ id: alert.id, is_active: !alert.is_active })}
            aria-pressed={alert.is_active}
            title={alert.is_active ? "E-mail attive (servono le impostazioni SMTP)" : "E-mail in pausa"}
            className="p-2 rounded-[var(--radius-sm)] text-[var(--muted-foreground)] hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
          >
            {alert.is_active ? <Bell className="h-4 w-4" /> : <BellOff className="h-4 w-4" />}
          </button>
          <button
            type="button"
            onClick={() => {
              if (window.confirm(`Eliminare la ricerca "${alert.name}"?`)) remove.mutate(alert.id);
            }}
            aria-label={`Elimina ${alert.name}`}
            className="p-2 rounded-[var(--radius-sm)] text-[var(--muted-foreground)] hover:bg-[var(--muted)] hover:text-[var(--destructive)]"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {describe(base).map((label) => (
          <span key={label} className="px-2 py-0.5 rounded-full bg-[var(--muted)] text-xs">{label}</span>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        {/* Opening the news counts as having seen them; the link keeps the
            timestamp, so the results stay the same after the reset. */}
        {alert.new_count > 0 && (
          <Link
            href={`/search${toQueryString({ ...base, first_seen_after: since })}`}
            onClick={() => markSeen.mutate(alert.id)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[var(--primary)] text-[var(--primary-foreground)] font-medium hover:opacity-90"
          >
            <Sparkles className="h-3.5 w-3.5" /> {alert.new_count} nuovi
          </Link>
        )}
        {alert.price_drop_count > 0 && (
          <Link
            href={`/search${toQueryString({ ...base, price_drop_since: since })}`}
            onClick={() => markSeen.mutate(alert.id)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[var(--positive-bg)] text-[var(--positive)] border border-[var(--positive-border)] font-medium hover:opacity-80"
          >
            <TrendingDown className="h-3.5 w-3.5" /> {alert.price_drop_count} ribassi
          </Link>
        )}
        <Link
          href={`/search${toQueryString(base)}`}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-[var(--border)] hover:border-[var(--primary)] hover:text-[var(--primary)]"
        >
          <Search className="h-3.5 w-3.5" /> Tutti ({alert.total.toLocaleString("it-IT")})
        </Link>
        {hasNews && (
          <button
            type="button"
            onClick={() => markSeen.mutate(alert.id)}
            className="inline-flex items-center gap-1.5 px-2 py-1.5 text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
          >
            <CheckCheck className="h-3.5 w-3.5" /> Segna come visti
          </button>
        )}
      </div>
    </li>
  );
}

export default function AlertsPage() {
  const { data, isLoading, isError } = useAlerts();
  const alerts = data ?? [];

  return (
    <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6">
      <h1 className="text-2xl font-bold flex items-center gap-2">
        <Bell className="h-6 w-6 text-[var(--primary)]" /> Ricerche salvate
      </h1>
      <p className="mt-1 text-sm text-[var(--muted-foreground)]">
        Nuovi annunci e ribassi di prezzo dall&apos;ultima volta che le hai guardate.
      </p>

      {isLoading && <p className="mt-6 text-sm text-[var(--muted-foreground)] animate-pulse">Caricamento…</p>}
      {isError && (
        <p role="alert" className="mt-6 text-sm text-[var(--destructive)]">
          Impossibile caricare le ricerche salvate. Il backend è raggiungibile?
        </p>
      )}

      {!isLoading && !isError && alerts.length === 0 && (
        <div className="mt-16 flex flex-col items-center text-center gap-3 text-[var(--muted-foreground)]">
          <Bell className="h-12 w-12 opacity-30" />
          <p className="text-base font-medium text-[var(--foreground)]">Nessuna ricerca salvata</p>
          <p className="text-sm max-w-sm">
            Imposta i filtri in Cerca e premi &laquo;Salva ricerca&raquo;: qui vedrai cosa cambia dopo ogni scansione.
          </p>
          <Link
            href="/search"
            className="mt-2 inline-flex items-center gap-1.5 px-4 py-2 rounded-full bg-[var(--primary)] text-[var(--primary-foreground)] text-sm font-medium hover:opacity-90"
          >
            <Search className="h-4 w-4" /> Vai alla ricerca
          </Link>
        </div>
      )}

      {alerts.length > 0 && (
        <ul className="mt-6 space-y-3">
          {alerts.map((a) => <AlertCard key={a.id} alert={a} />)}
        </ul>
      )}
    </div>
  );
}
