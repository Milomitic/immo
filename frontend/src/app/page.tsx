"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import Link from "next/link";
import { Search, MapPin, ArrowRight, Map as MapIcon, Sparkles, RefreshCw, Loader2 } from "lucide-react";
import { useStats } from "@/hooks/useListings";
import { useScrapeStatus, useTriggerScrape } from "@/hooks/useScrapeStatus";
import { formatPrice, portalLabel } from "@/lib/utils";

export default function HomePage() {
  const router = useRouter();
  const [city, setCity] = useState("");
  const [listingType, setListingType] = useState("sale");
  const { data: stats } = useStats();
  const { data: scrapeStatus } = useScrapeStatus();
  const triggerScrape = useTriggerScrape();
  const isRunning = scrapeStatus?.is_running ?? false;

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const params = new URLSearchParams();
    if (city) params.set("city", city.toLowerCase());
    params.set("listing_type", listingType);
    router.push(`/search?${params}`);
  };

  const topCities = stats ? Object.entries(stats.by_city).slice(0, 8) : [];
  const portalCount = stats ? Object.keys(stats.by_portal).length : 0;

  return (
    <div className="min-h-[calc(100vh-3.5rem)] relative overflow-hidden">
      {/* Animated background — three soft blobs that drift and pulse.
          Pure CSS, no JS overhead, sits behind everything. */}
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
        <div className="absolute -top-32 -left-32 h-96 w-96 rounded-full bg-[var(--primary)]/15 blur-3xl animate-blob" />
        <div className="absolute top-1/3 -right-32 h-[28rem] w-[28rem] rounded-full bg-emerald-400/15 blur-3xl animate-blob animation-delay-2000" />
        <div className="absolute -bottom-40 left-1/3 h-[26rem] w-[26rem] rounded-full bg-amber-400/15 blur-3xl animate-blob animation-delay-4000" />
      </div>

      {/* Hero */}
      <section className="py-16 sm:py-24 lg:py-28 relative">
        <div className="mx-auto max-w-3xl px-4 text-center">
          <div className="flex flex-wrap items-center justify-center gap-2 mb-5 animate-fade-up">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[var(--primary)]/10 text-[var(--primary)] text-xs font-semibold">
              <Sparkles className="h-3.5 w-3.5" />
              6 portali aggregati, deduplicati in un solo posto
            </span>
            {/* "Scan-style" button — kicks off a scrape, the persistent
                toast at bottom-right then takes over the progress
                feedback. Disabled while a scrape is already running so
                we don't queue duplicate jobs. */}
            <button
              onClick={() => triggerScrape.mutate({})}
              disabled={isRunning || triggerScrape.isPending}
              title={isRunning ? "Aggiornamento già in corso" : "Avvia aggiornamento da tutti i portali"}
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[var(--foreground)] text-[var(--background)] text-xs font-semibold transition-opacity disabled:opacity-50 disabled:cursor-not-allowed hover:opacity-90"
            >
              {isRunning || triggerScrape.isPending ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Aggiornamento in corso
                </>
              ) : (
                <>
                  <RefreshCw className="h-3.5 w-3.5" />
                  Aggiorna annunci
                </>
              )}
            </button>
          </div>
          <h1 className="text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-[var(--foreground)] mb-4 animate-fade-up animation-delay-100">
            Cerca casa su tutti i portali,<br />
            <span className="text-[var(--primary)]">in un unico posto</span>
          </h1>
          <p className="text-base sm:text-lg text-[var(--muted-foreground)] mb-8 max-w-xl mx-auto animate-fade-up animation-delay-200">
            Aggreghiamo annunci da Immobiliare.it, Casa.it, Tecnocasa, RE/MAX,
            Gabetti e Vistocasa — confrontabili in lista o sulla mappa.
          </p>

          {/* Search Form */}
          <form onSubmit={handleSearch} className="max-w-xl mx-auto animate-fade-up animation-delay-300">
            <div className="flex gap-2 p-2 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--background)]" style={{ boxShadow: "0 8px 32px rgba(0,0,0,0.10)" }}>
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--muted-foreground)]" />
                <input
                  type="text"
                  value={city}
                  onChange={(e) => setCity(e.target.value)}
                  placeholder="In quale citta cerchi?"
                  className="w-full pl-10 pr-3 py-2.5 rounded-[var(--radius-md)] bg-transparent text-sm focus:outline-none"
                />
              </div>
              <select
                value={listingType}
                onChange={(e) => setListingType(e.target.value)}
                className="px-3 py-2 rounded-[var(--radius-md)] bg-[var(--muted)] text-sm font-medium focus:outline-none shrink-0"
              >
                <option value="sale">Vendita</option>
                <option value="rent">Affitto</option>
              </select>
              <button
                type="submit"
                className="px-5 py-2.5 bg-[var(--primary)] text-[var(--primary-foreground)] rounded-[var(--radius-md)] text-sm font-semibold hover:opacity-90 transition-opacity shrink-0"
              >
                Cerca
              </button>
            </div>
          </form>

          {/* Category pills */}
          <div className="flex flex-wrap justify-center gap-2 mt-6 animate-fade-up animation-delay-400">
            {[
              { label: "Appartamenti", type: "apartment" },
              { label: "Case", type: "house" },
              { label: "Ville", type: "villa" },
              { label: "Loft", type: "loft" },
            ].map(({ label, type }) => (
              <Link
                key={type}
                href={`/search?property_type=${type}&listing_type=sale`}
                className="px-4 py-1.5 rounded-full text-sm font-medium border border-[var(--border)] text-[var(--muted-foreground)] hover:border-[var(--primary)] hover:text-[var(--primary)] transition-colors hover:-translate-y-0.5 transform duration-150"
              >
                {label}
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* Map promo — large CTA so the feature is impossible to miss
          for first-time visitors. Same gradient palette as the blobs. */}
      <section className="px-4 -mt-4 sm:mt-0 mb-12 sm:mb-16">
        <Link
          href="/map"
          className="group relative mx-auto max-w-5xl flex items-center gap-4 sm:gap-6 p-5 sm:p-7 rounded-[var(--radius-lg)] border border-[var(--border)] bg-gradient-to-br from-[var(--primary)]/8 via-emerald-400/5 to-amber-400/5 hover:border-[var(--primary)] hover:shadow-[var(--card-hover-shadow)] transition-all overflow-hidden"
        >
          {/* Decorative pulse dot */}
          <span className="absolute top-4 right-5 hidden sm:flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--primary)] opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--primary)]" />
          </span>
          <div className="shrink-0 h-14 w-14 sm:h-16 sm:w-16 rounded-[var(--radius-md)] bg-[var(--primary)] text-[var(--primary-foreground)] flex items-center justify-center shadow-lg group-hover:scale-110 transition-transform">
            <MapIcon className="h-7 w-7 sm:h-8 sm:w-8" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-base sm:text-lg font-bold mb-0.5">Esplora gli annunci sulla mappa</div>
            <div className="text-xs sm:text-sm text-[var(--muted-foreground)]">
              Visualizza i prezzi geolocalizzati, scrolla la lista e clicca i pin per i dettagli.
            </div>
          </div>
          <ArrowRight className="shrink-0 h-5 w-5 text-[var(--muted-foreground)] group-hover:text-[var(--primary)] group-hover:translate-x-1 transition-all" />
        </Link>
      </section>

      {/* Stats bar */}
      {stats && stats.active_listings > 0 && (
        <section className="border-y border-[var(--border)] bg-[var(--muted)]/40 backdrop-blur">
          <div className="mx-auto max-w-5xl px-4 py-4">
            <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-2 text-sm">
              <span>
                <span className="font-bold text-[var(--foreground)]">{stats.active_listings.toLocaleString("it-IT")}</span>
                <span className="text-[var(--muted-foreground)]"> annunci attivi</span>
              </span>
              <span className="hidden sm:inline text-[var(--border)]">|</span>
              <span>
                <span className="font-bold text-[var(--foreground)]">{Object.keys(stats.by_city).length}</span>
                <span className="text-[var(--muted-foreground)]"> citta</span>
              </span>
              <span className="hidden sm:inline text-[var(--border)]">|</span>
              <span>
                <span className="font-bold text-[var(--foreground)]">{portalCount}</span>
                <span className="text-[var(--muted-foreground)]"> portali</span>
              </span>
              <span className="hidden sm:inline text-[var(--border)]">|</span>
              <div className="flex items-center gap-2 flex-wrap justify-center">
                {Object.entries(stats.by_portal).map(([portal, count]) => (
                  <Link
                    key={portal}
                    href={`/search?source_portal=${portal}&listing_type=sale`}
                    className="inline-flex items-center rounded-[var(--radius-sm)] border border-[var(--border)] bg-[var(--background)] px-2 py-0.5 text-xs font-medium hover:border-[var(--primary)] hover:text-[var(--primary)] transition-colors"
                  >
                    {portalLabel(portal)} ({count.toLocaleString("it-IT")})
                  </Link>
                ))}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Popular cities */}
      {topCities.length > 0 && (
        <section className="py-12 sm:py-16">
          <div className="mx-auto max-w-5xl px-4 sm:px-6">
            <h2 className="text-xl font-bold mb-6 text-center">Citta piu cercate</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
              {topCities.map(([cityName, count]) => {
                const avgPrice = stats?.avg_price_sqm_by_city[cityName];
                return (
                  <Link
                    key={cityName}
                    href={`/search?city=${cityName}&listing_type=sale`}
                    className="group rounded-[var(--radius-md)] border border-[var(--border)] p-4 hover:border-[var(--primary)] hover:shadow-[var(--card-hover-shadow)] hover:-translate-y-0.5 transform transition-all"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-1.5">
                        <MapPin className="h-4 w-4 text-[var(--primary)]" />
                        <span className="text-sm font-semibold capitalize">{cityName}</span>
                      </div>
                      <ArrowRight className="h-3.5 w-3.5 text-[var(--muted-foreground)] group-hover:text-[var(--primary)] group-hover:translate-x-0.5 transition-all" />
                    </div>
                    <div className="text-xs text-[var(--muted-foreground)]">
                      {count.toLocaleString("it-IT")} annunci
                    </div>
                    {avgPrice && avgPrice < 50000 && (
                      <div className="text-xs text-[var(--muted-foreground)] mt-0.5">
                        Media {formatPrice(avgPrice)}/m&sup2;
                      </div>
                    )}
                  </Link>
                );
              })}
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
