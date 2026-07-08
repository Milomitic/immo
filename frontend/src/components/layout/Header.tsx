"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Home, Search, GitCompare, Map as MapIcon, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

// Filter-related params we want to carry across /search → /map navigation
// so the user doesn't lose their selections when toggling views.
// Note: ``bbox`` is intentionally NOT preserved — it's viewport-specific
// to the map and would over-clip the search list. ``polygon`` *is*
// preserved because it's a deliberate user-drawn perimeter.
const PRESERVED_PARAMS = new Set([
  "q", "city", "zone", "province",
  "listing_type", "property_type",
  "price_min", "price_max", "area_min", "area_max",
  "rooms_min", "rooms_max", "bedrooms_min", "bathrooms_min",
  "energy_class", "condition", "source_portal",
  "has_elevator", "has_balcony", "has_terrace", "has_garage", "has_garden",
  "floor_min", "floor_max",
  "price_per_sqm_min", "price_per_sqm_max",
  "year_built_min", "year_built_max",
  "polygon",
  "sort", "page_size",
]);

function preserveFilterQuery(searchParams: URLSearchParams): string {
  const out = new URLSearchParams();
  searchParams.forEach((v, k) => {
    if (PRESERVED_PARAMS.has(k)) out.set(k, v);
  });
  const s = out.toString();
  return s ? `?${s}` : "";
}

export function Header() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const searchParams = useSearchParams();
  const filterQs = preserveFilterQuery(new URLSearchParams(searchParams.toString()));

  return (
    <header className="border-b border-[var(--border)] bg-[var(--background)] sticky top-0 z-30">
      <div className="mx-auto max-w-[var(--content-max)] px-4 sm:px-6 lg:px-8">
        <div className="flex h-14 items-center justify-between">
          <Link href="/" className="flex items-center gap-2 text-lg font-bold text-[var(--primary)] hover:opacity-80 transition-opacity">
            <Home className="h-5 w-5" />
            Immo
          </Link>

          <nav className="flex items-center gap-1">
            <Link
              href={`/search${filterQs}`}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-sm)] text-sm font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--muted)] transition-colors"
            >
              <Search className="h-4 w-4" />
              <span className="hidden sm:inline">Cerca</span>
            </Link>
            {/* Promoted CTA — solid pill so the map view stands out
                more than a flat link in the nav row. */}
            <Link
              href={`/map${filterQs}`}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-semibold bg-[var(--primary)] text-[var(--primary-foreground)] shadow-sm hover:opacity-90 transition-all hover:shadow-md"
            >
              <MapIcon className="h-4 w-4" />
              <span className="hidden sm:inline">Mappa</span>
            </Link>
            <Link
              href="/compare"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-sm)] text-sm font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--muted)] transition-colors"
            >
              <GitCompare className="h-4 w-4" />
              <span className="hidden sm:inline">Confronta</span>
            </Link>
            {mounted && (
              <button
                onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                className="flex items-center justify-center w-9 h-9 rounded-[var(--radius-sm)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--muted)] transition-colors"
                title={theme === "dark" ? "Tema chiaro" : "Tema scuro"}
              >
                {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              </button>
            )}
          </nav>
        </div>
      </div>
    </header>
  );
}
