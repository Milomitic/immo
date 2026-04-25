"use client";

import Link from "next/link";
import { Home, Search, GitCompare, Map as MapIcon, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

export function Header() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

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
              href="/search"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-sm)] text-sm font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--muted)] transition-colors"
            >
              <Search className="h-4 w-4" />
              <span className="hidden sm:inline">Cerca</span>
            </Link>
            <Link
              href="/map"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-sm)] text-sm font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--muted)] transition-colors"
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
