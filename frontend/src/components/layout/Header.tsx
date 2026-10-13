"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Bell, Home, Search, GitCompare, Heart, Map as MapIcon, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { useAlerts } from "@/hooks/useAlerts";
import { useFavoriteIds } from "@/hooks/useFavorites";
import { FILTER_PARAM_KEYS, SINCE_PARAM_KEYS, VIEW_PARAM_KEYS, pickParams, toQueryString } from "@/lib/filterParams";

// Carried across /search ↔ /map so switching views keeps the selection.
const PRESERVED_PARAMS = [...FILTER_PARAM_KEYS, ...SINCE_PARAM_KEYS, ...VIEW_PARAM_KEYS];

export function Header() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const searchParams = useSearchParams();
  const filterQs = toQueryString(pickParams(new URLSearchParams(searchParams.toString()), PRESERVED_PARAMS));
  const { ids: favoriteIds } = useFavoriteIds();
  const { data: alerts } = useAlerts();
  const alertNews = (alerts ?? []).reduce((n, a) => n + a.new_count + a.price_drop_count, 0);

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
              href="/favorites"
              className="relative flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-sm)] text-sm font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--muted)] transition-colors"
              aria-label={`Preferiti (${favoriteIds.size})`}
            >
              <Heart className="h-4 w-4" />
              <span className="hidden sm:inline">Preferiti</span>
              {favoriteIds.size > 0 && (
                <span className="min-w-4 h-4 px-1 rounded-full bg-red-500 text-white text-[10px] font-bold leading-4 text-center">
                  {favoriteIds.size}
                </span>
              )}
            </Link>
            <Link
              href="/alerts"
              className="relative flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-sm)] text-sm font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--muted)] transition-colors"
              aria-label={alertNews > 0 ? `Ricerche salvate (${alertNews} novità)` : "Ricerche salvate"}
            >
              <Bell className="h-4 w-4" />
              <span className="hidden sm:inline">Avvisi</span>
              {alertNews > 0 && (
                <span className="min-w-4 h-4 px-1 rounded-full bg-[var(--primary)] text-[var(--primary-foreground)] text-[10px] font-bold leading-4 text-center">
                  {alertNews > 99 ? "99+" : alertNews}
                </span>
              )}
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
