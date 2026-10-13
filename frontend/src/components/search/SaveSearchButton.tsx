"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Bell, Check } from "lucide-react";
import { useCreateAlert } from "@/hooks/useAlerts";
import { FILTER_PARAM_KEYS, pickParams } from "@/lib/filterParams";
import { formatPriceCompact, propertyTypeLabel } from "@/lib/utils";

/** A readable default name built from the active filters. */
function suggestName(f: Record<string, string>): string {
  const parts: string[] = [];
  if (f.city) parts.push(f.city.charAt(0).toUpperCase() + f.city.slice(1));
  if (f.zone) parts.push(f.zone);
  if (f.property_type) parts.push(propertyTypeLabel(f.property_type));
  if (f.listing_type === "rent") parts.push("affitto");
  if (f.price_max) parts.push(`fino a €${formatPriceCompact(Number(f.price_max))}`);
  else if (f.price_min) parts.push(`da €${formatPriceCompact(Number(f.price_min))}`);
  if (f.rooms_min) parts.push(`${f.rooms_min}+ locali`);
  if (f.polygon) parts.push("area disegnata");
  if (f.q) parts.push(`"${f.q}"`);
  return (parts.join(" · ") || "Tutti gli annunci").slice(0, 80);
}

export function SaveSearchButton() {
  const searchParams = useSearchParams();
  const create = useCreateAlert();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const filters = pickParams(new URLSearchParams(searchParams.toString()), FILTER_PARAM_KEYS);

  // The "saved" tick is a confirmation, not a state: fade back to the
  // button so another search can be saved.
  const { isSuccess, reset } = create;
  useEffect(() => {
    if (!isSuccess) return;
    const t = setTimeout(reset, 4000);
    return () => clearTimeout(t);
  }, [isSuccess, reset]);

  if (create.isSuccess) {
    return (
      <Link
        href="/alerts"
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-sm)] text-sm font-medium text-[var(--positive)] border border-[var(--positive-border)] bg-[var(--positive-bg)]"
      >
        <Check className="h-4 w-4" /> Salvata · vedi avvisi
      </Link>
    );
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => {
          setName(suggestName(filters));
          setOpen((o) => !o);
        }}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-sm)] border border-[var(--border)] text-sm font-medium hover:border-[var(--primary)] hover:text-[var(--primary)] transition-colors"
      >
        <Bell className="h-4 w-4" /> Salva ricerca
      </button>

      {open && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate({ name: name.trim() || suggestName(filters), filters }, { onSuccess: () => setOpen(false) });
          }}
          onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
          className="absolute right-0 top-full mt-2 z-20 w-72 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--background)] p-3 shadow-lg space-y-2"
        >
          <label className="block text-xs font-medium text-[var(--muted-foreground)]" htmlFor="save-search-name">
            Nome della ricerca
          </label>
          <input
            id="save-search-name"
            autoFocus
            value={name}
            maxLength={80}
            onChange={(e) => setName(e.target.value)}
            className="w-full px-2.5 py-1.5 rounded-[var(--radius-sm)] border border-[var(--border)] bg-[var(--background)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
          />
          <p className="text-[11px] text-[var(--muted-foreground)]">
            Ti segnaleremo i nuovi annunci e i ribassi di prezzo per questi filtri.
          </p>
          {create.isError && (
            <p role="alert" className="text-xs text-[var(--destructive)]">
              {create.error instanceof Error ? create.error.message : "Salvataggio non riuscito"}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="px-3 py-1.5 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            >
              Annulla
            </button>
            <button
              type="submit"
              disabled={create.isPending}
              className="px-3 py-1.5 rounded-[var(--radius-sm)] bg-[var(--primary)] text-[var(--primary-foreground)] text-sm font-medium hover:opacity-90 disabled:opacity-60"
            >
              {create.isPending ? "Salvataggio…" : "Salva"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
