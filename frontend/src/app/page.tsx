"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import Link from "next/link";
import { Search, Building2, MapPin, TrendingUp, ArrowRight } from "lucide-react";
import { useStats } from "@/hooks/useListings";
import { formatPrice, portalLabel } from "@/lib/utils";

export default function HomePage() {
  const router = useRouter();
  const [city, setCity] = useState("");
  const [listingType, setListingType] = useState("sale");
  const { data: stats } = useStats();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const params = new URLSearchParams();
    if (city) params.set("city", city.toLowerCase());
    params.set("listing_type", listingType);
    router.push(`/search?${params}`);
  };

  const topCities = stats ? Object.entries(stats.by_city).slice(0, 8) : [];

  return (
    <div className="min-h-[calc(100vh-4rem)]">
      {/* Hero */}
      <section className="py-16 sm:py-24 lg:py-32">
        <div className="mx-auto max-w-3xl px-4 text-center">
          <h1 className="text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-[var(--foreground)] mb-4">
            Cerca casa su tutti i portali,<br />
            <span className="text-[var(--primary)]">in un unico posto</span>
          </h1>
          <p className="text-base sm:text-lg text-[var(--muted-foreground)] mb-8 max-w-xl mx-auto">
            Aggreghiamo annunci da Immobiliare.it e Casa.it.
            Deduplicati e confrontabili in una sola ricerca.
          </p>

          {/* Search Form */}
          <form onSubmit={handleSearch} className="max-w-xl mx-auto">
            <div className="flex gap-2 p-2 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--background)]" style={{ boxShadow: "0 4px 24px rgba(0,0,0,0.08)" }}>
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
          <div className="flex flex-wrap justify-center gap-2 mt-6">
            {[
              { label: "Appartamenti", type: "apartment" },
              { label: "Case", type: "house" },
              { label: "Ville", type: "villa" },
              { label: "Loft", type: "loft" },
            ].map(({ label, type }) => (
              <Link
                key={type}
                href={`/search?property_type=${type}&listing_type=sale`}
                className="px-4 py-1.5 rounded-full text-sm font-medium border border-[var(--border)] text-[var(--muted-foreground)] hover:border-[var(--primary)] hover:text-[var(--primary)] transition-colors"
              >
                {label}
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* Stats bar */}
      {stats && stats.active_listings > 0 && (
        <section className="border-y border-[var(--border)] bg-[var(--muted)]">
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
              <div className="flex items-center gap-2">
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
                    className="group rounded-[var(--radius-md)] border border-[var(--border)] p-4 hover:border-[var(--primary)] hover:shadow-[var(--card-hover-shadow)] transition-all"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-1.5">
                        <MapPin className="h-4 w-4 text-[var(--primary)]" />
                        <span className="text-sm font-semibold capitalize">{cityName}</span>
                      </div>
                      <ArrowRight className="h-3.5 w-3.5 text-[var(--muted-foreground)] group-hover:text-[var(--primary)] transition-colors" />
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
