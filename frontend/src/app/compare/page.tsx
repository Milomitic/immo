"use client";

import { Suspense, type ReactNode } from "react";
import { useSearchParams } from "next/navigation";
import { useQueries } from "@tanstack/react-query";
import { fetchListing } from "@/lib/api";
import type { ListingDetail } from "@/lib/types";
import { formatPrice, formatArea, portalLabel, portalColor, propertyTypeLabel, floorLabel, conditionLabel, energyClassColor, imageVariant } from "@/lib/utils";
import { ArrowLeft, CheckCircle2, XCircle, Minus, Search } from "lucide-react";
import Link from "next/link";
import { Badge } from "@/components/ui/Badge";

export default function ComparePage() {
  return (
    <Suspense fallback={<div className="flex justify-center py-20"><div className="h-8 w-8 animate-spin rounded-full border-4 border-[var(--primary)] border-t-transparent" /></div>}>
      <CompareContent />
    </Suspense>
  );
}

function CompareContent() {
  const searchParams = useSearchParams();
  const idsParam = searchParams.get("ids");
  const ids = idsParam ? idsParam.split(",").slice(0, 3) : [];

  // useQueries, not useQuery-in-a-loop: the number of ids comes from the
  // URL and can change between renders, which breaks the rules of hooks.
  const queries = useQueries({
    queries: ids.map((id) => ({
      queryKey: ["listing", id],
      queryFn: () => fetchListing(id),
    })),
  });

  const listings = queries
    .map((q) => q.data)
    .filter((l): l is ListingDetail => Boolean(l));
  const isLoading = queries.some((q) => q.isLoading);

  if (ids.length === 0) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-20 text-center">
        <Search className="h-12 w-12 mx-auto mb-4 text-[var(--muted-foreground)] opacity-40" />
        <h1 className="text-2xl font-bold mb-3">Confronta annunci</h1>
        <p className="text-[var(--muted-foreground)] mb-6">
          Seleziona 2 o 3 annunci dalla pagina di ricerca usando il checkbox &ldquo;Confronta&rdquo; sulle card.
        </p>
        <Link href="/search" className="inline-flex items-center gap-2 px-5 py-2.5 rounded-[var(--radius-md)] bg-[var(--primary)] text-[var(--primary-foreground)] text-sm font-semibold hover:opacity-90 transition-opacity">
          Vai alla ricerca
        </Link>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-[var(--primary)] border-t-transparent" />
      </div>
    );
  }

  const BoolIcon = ({ value }: { value: boolean | null }) => {
    if (value === true) return <CheckCircle2 className="h-4 w-4 text-[var(--success)] mx-auto" />;
    if (value === false) return <XCircle className="h-4 w-4 text-red-400 mx-auto" />;
    return <Minus className="h-4 w-4 text-[var(--muted-foreground)] mx-auto" />;
  };

  const rows: { label: string; render: (l: ListingDetail) => ReactNode }[] = [
    { label: "Prezzo", render: (l) => <span className="font-bold text-[var(--primary)]">{formatPrice(l.price)}</span> },
    { label: "Prezzo/m\u00B2", render: (l) => l.price_per_sqm ? formatPrice(l.price_per_sqm) : "N/D" },
    { label: "Superficie", render: (l) => l.area_sqm ? formatArea(l.area_sqm) : "N/D" },
    { label: "Locali", render: (l) => l.rooms ?? "N/D" },
    { label: "Bagni", render: (l) => l.bathrooms ?? "N/D" },
    { label: "Piano", render: (l) => l.floor ? floorLabel(l.floor) : "N/D" },
    { label: "Tipologia", render: (l) => propertyTypeLabel(l.property_type) },
    { label: "Classe energetica", render: (l) => l.energy_class ? <Badge size="sm" className={energyClassColor(l.energy_class)}>Classe {l.energy_class}</Badge> : "N/D" },
    { label: "Stato", render: (l) => l.condition ? conditionLabel(l.condition) : "N/D" },
    { label: "Citta", render: (l) => <span className="capitalize">{l.city}</span> },
    { label: "Portale", render: (l) => <Badge size="sm" className={`${portalColor(l.source_portal)} text-white`}>{portalLabel(l.source_portal)}</Badge> },
    { label: "Fonti", render: (l) => l.source_count },
    { label: "Ascensore", render: (l) => <BoolIcon value={l.has_elevator} /> },
    { label: "Balcone", render: (l) => <BoolIcon value={l.has_balcony} /> },
    { label: "Terrazzo", render: (l) => <BoolIcon value={l.has_terrace} /> },
    { label: "Garage", render: (l) => <BoolIcon value={l.has_garage} /> },
    { label: "Giardino", render: (l) => <BoolIcon value={l.has_garden} /> },
  ];

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:px-8">
      <Link href="/search" className="inline-flex items-center gap-1 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)] mb-4">
        <ArrowLeft className="h-4 w-4" /> Torna ai risultati
      </Link>

      <h1 className="text-2xl font-bold mb-6">Confronto annunci</h1>

      <div className="overflow-x-auto rounded-[var(--radius-lg)] border border-[var(--border)]">
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-[var(--muted)]">
              <th className="text-left p-4 text-sm font-semibold text-[var(--muted-foreground)] w-40" />
              {listings.map((listing) => (
                <th key={listing!.id} className="p-4 text-left min-w-[200px]">
                  <div className="space-y-2">
                    {listing!.images[0] && (
                      <img src={imageVariant(listing!.images[0], "card")} alt="" referrerPolicy="no-referrer" className="w-full h-32 object-cover rounded-[var(--radius-md)]" />
                    )}
                    <Link href={`/listing/${listing!.id}`} className="text-sm font-semibold hover:text-[var(--primary)] line-clamp-2 block transition-colors">
                      {listing!.title}
                    </Link>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(({ label, render }, i) => (
              <tr key={label} className={i % 2 === 0 ? "" : "bg-[var(--muted)]/50"}>
                <td className="p-3 text-sm font-medium text-[var(--muted-foreground)] border-r border-[var(--border)]">{label}</td>
                {listings.map((listing) => (
                  <td key={listing!.id} className="p-3 text-sm">{render(listing)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
