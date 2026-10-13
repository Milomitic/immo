"use client";

import { useQueryState, parseAsInteger, parseAsString, parseAsBoolean } from "nuqs";
import { FilterSection } from "./FilterSection";
import { cn } from "@/lib/utils";
import type { ListingSearchParams } from "@/lib/types";

function NumberButton({ value, label, current, onClick }: { value: number; label: string; current: number | null; onClick: (v: number | null) => void }) {
  const active = current === value;
  return (
    <button
      onClick={() => onClick(active ? null : value)}
      className={cn(
        "h-9 min-w-9 px-2 rounded-[var(--radius-sm)] text-sm font-medium border transition-all",
        active
          ? "bg-[var(--primary)] text-[var(--primary-foreground)] border-[var(--primary)] shadow-sm"
          : "border-[var(--border)] text-[var(--foreground)] hover:border-[var(--primary)] hover:text-[var(--primary)]"
      )}
    >
      {label}
    </button>
  );
}

function PillButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "px-3.5 py-1.5 rounded-full text-sm font-medium border transition-all",
        active
          ? "bg-[var(--primary)] text-[var(--primary-foreground)] border-[var(--primary)] shadow-sm"
          : "border-[var(--border)] hover:border-[var(--primary)] hover:text-[var(--primary)]"
      )}
    >
      {label}
    </button>
  );
}

function Checkbox({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2.5 cursor-pointer group">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 rounded border-[var(--border)] text-[var(--primary)] accent-[var(--primary)]"
      />
      <span className="text-sm text-[var(--foreground)] group-hover:text-[var(--primary)] transition-colors">{label}</span>
    </label>
  );
}

/**
 * Shared hook that owns every listing-filter nuqs subscription. Any place
 * that needs the active filter count or a "reset all" callback can call this
 * — re-subscribing on the same URL keys is cheap and keeps writes consistent.
 */
export function useListingFilters() {
  const [city, setCity] = useQueryState("city", parseAsString);
  const [zone, setZone] = useQueryState("zone", parseAsString);
  const [listingType, setListingType] = useQueryState("listing_type", parseAsString);
  const [propertyType, setPropertyType] = useQueryState("property_type", parseAsString);
  const [priceMin, setPriceMin] = useQueryState("price_min", parseAsInteger);
  const [priceMax, setPriceMax] = useQueryState("price_max", parseAsInteger);
  const [areaMin, setAreaMin] = useQueryState("area_min", parseAsInteger);
  const [areaMax, setAreaMax] = useQueryState("area_max", parseAsInteger);
  const [roomsMin, setRoomsMin] = useQueryState("rooms_min", parseAsInteger);
  const [bathroomsMin, setBathroomsMin] = useQueryState("bathrooms_min", parseAsInteger);
  const [energyClass, setEnergyClass] = useQueryState("energy_class", parseAsString);
  const [condition, setCondition] = useQueryState("condition", parseAsString);
  const [floorMin, setFloorMin] = useQueryState("floor_min", parseAsInteger);
  const [floorMax, setFloorMax] = useQueryState("floor_max", parseAsInteger);
  const [hasElevator, setHasElevator] = useQueryState("has_elevator", parseAsBoolean);
  const [hasBalcony, setHasBalcony] = useQueryState("has_balcony", parseAsBoolean);
  const [hasTerrace, setHasTerrace] = useQueryState("has_terrace", parseAsBoolean);
  const [hasGarage, setHasGarage] = useQueryState("has_garage", parseAsBoolean);
  const [hasGarden, setHasGarden] = useQueryState("has_garden", parseAsBoolean);
  const [sourcePortal, setSourcePortal] = useQueryState("source_portal", parseAsString);
  // Set by saved-search links ("vedi i nuovi"); removable like any filter.
  const [firstSeenAfter, setFirstSeenAfter] = useQueryState("first_seen_after", parseAsString);
  const [priceDropSince, setPriceDropSince] = useQueryState("price_drop_since", parseAsString);
  const [publishedWithinDays, setPublishedWithinDays] = useQueryState("published_within_days", parseAsInteger);
  const [publishedAfter, setPublishedAfter] = useQueryState("published_after", parseAsString);
  const [isAuction, setIsAuction] = useQueryState("is_auction", parseAsBoolean);

  const values = {
    city, zone, listingType, propertyType,
    priceMin, priceMax, areaMin, areaMax,
    roomsMin, bathroomsMin, floorMin, floorMax,
    energyClass, condition,
    hasElevator, hasBalcony, hasTerrace, hasGarage, hasGarden,
    sourcePortal, firstSeenAfter, priceDropSince,
    publishedWithinDays, publishedAfter, isAuction,
  };
  const setters = {
    setCity, setZone, setListingType, setPropertyType,
    setPriceMin, setPriceMax, setAreaMin, setAreaMax,
    setRoomsMin, setBathroomsMin, setFloorMin, setFloorMax,
    setEnergyClass, setCondition,
    setHasElevator, setHasBalcony, setHasTerrace, setHasGarage, setHasGarden,
    setSourcePortal, setFirstSeenAfter, setPriceDropSince,
    setPublishedWithinDays, setPublishedAfter, setIsAuction,
  };

  const activeCount = Object.values(values).filter((v) => v !== null && v !== undefined).length;

  const clearAll = () => {
    setCity(null); setZone(null); setListingType(null); setPropertyType(null);
    setPriceMin(null); setPriceMax(null); setAreaMin(null); setAreaMax(null);
    setRoomsMin(null); setBathroomsMin(null); setFloorMin(null); setFloorMax(null);
    setEnergyClass(null); setCondition(null);
    setHasElevator(null); setHasBalcony(null); setHasTerrace(null); setHasGarage(null); setHasGarden(null);
    setSourcePortal(null); setFirstSeenAfter(null); setPriceDropSince(null);
    setPublishedWithinDays(null); setPublishedAfter(null); setIsAuction(null);
  };

  return { values, setters, activeCount, clearAll };
}

export type ListingFilterValues = ReturnType<typeof useListingFilters>["values"];

/**
 * The single place that turns sidebar filter state into API params.
 * /search and /map both spread this, so a filter can't be wired on one
 * page and forgotten on the other (that's how "Stato immobile" silently
 * did nothing on /search).
 */
export function filtersToParams(v: ListingFilterValues): ListingSearchParams {
  return {
    city: v.city || undefined,
    zone: v.zone || undefined,
    listing_type: v.listingType || undefined,
    property_type: v.propertyType || undefined,
    price_min: v.priceMin || undefined,
    price_max: v.priceMax || undefined,
    area_min: v.areaMin || undefined,
    area_max: v.areaMax || undefined,
    rooms_min: v.roomsMin || undefined,
    bathrooms_min: v.bathroomsMin || undefined,
    floor_min: v.floorMin ?? undefined,
    floor_max: v.floorMax ?? undefined,
    energy_class: v.energyClass || undefined,
    condition: v.condition || undefined,
    has_elevator: v.hasElevator || undefined,
    has_balcony: v.hasBalcony || undefined,
    has_terrace: v.hasTerrace || undefined,
    has_garage: v.hasGarage || undefined,
    has_garden: v.hasGarden || undefined,
    source_portal: v.sourcePortal || undefined,
    first_seen_after: v.firstSeenAfter || undefined,
    price_drop_since: v.priceDropSince || undefined,
    published_within_days: v.publishedWithinDays || undefined,
    published_after: v.publishedAfter || undefined,
    // false is meaningful (hide auctions): don't let || swallow it.
    is_auction: v.isAuction ?? undefined,
  };
}

/** "Pubblicato" presets: calendar days including today. */
export const PUBLISHED_OPTIONS: { days: number; label: string }[] = [
  { days: 1, label: "Oggi" },
  { days: 3, label: "Ultimi 3 giorni" },
  { days: 7, label: "Ultima settimana" },
  { days: 14, label: "Ultime 2 settimane" },
  { days: 30, label: "Ultimo mese" },
  { days: 90, label: "Ultimi 3 mesi" },
];

interface FilterFieldsProps {
  showHeader?: boolean;
  /** "stack": accordion for sidebars and drawers. "grid": sections side
   *  by side, always open — the map's filter bar. */
  layout?: "stack" | "grid";
}

/**
 * The actual filter form fields. Layout-agnostic: can be dropped into a
 * sticky sidebar, a mobile drawer, or a map popover without extra chrome.
 */
export function FilterFields({ showHeader = true, layout = "stack" }: FilterFieldsProps) {
  const { values, setters, activeCount, clearAll } = useListingFilters();
  const {
    city, zone, listingType, propertyType,
    priceMin, priceMax, areaMin, areaMax,
    roomsMin, bathroomsMin, floorMin, floorMax,
    energyClass, condition,
    hasElevator, hasBalcony, hasTerrace, hasGarage, hasGarden,
    sourcePortal, publishedWithinDays, publishedAfter, isAuction,
  } = values;
  const {
    setCity, setZone, setListingType, setPropertyType,
    setPriceMin, setPriceMax, setAreaMin, setAreaMax,
    setRoomsMin, setBathroomsMin, setFloorMin, setFloorMax,
    setEnergyClass, setCondition,
    setHasElevator, setHasBalcony, setHasTerrace, setHasGarage, setHasGarden,
    setSourcePortal, setPublishedWithinDays, setPublishedAfter, setIsAuction,
  } = setters;
  const sectionProps = layout === "grid" ? { collapsible: false } : {};
  const today = new Date().toISOString().slice(0, 10);

  const inputClass = "w-full px-3 py-2 rounded-[var(--radius-sm)] border border-[var(--border)] bg-[var(--background)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--primary)] focus:border-transparent transition-shadow";

  return (
    <div>
      {showHeader && (
        <div className="flex items-center justify-between pb-3 border-b border-[var(--border)] mb-1">
          <h3 className="text-base font-bold">Filtri</h3>
          {activeCount > 0 && (
            <button onClick={clearAll} className="text-xs font-medium text-[var(--primary)] hover:underline">
              Resetta tutto
            </button>
          )}
        </div>
      )}

      <div className={layout === "grid" ? "grid gap-x-6 gap-y-5 sm:grid-cols-2 lg:grid-cols-4 2xl:grid-cols-6" : undefined}>
      <FilterSection {...sectionProps} title="Tipo" count={listingType ? 1 : 0}>
        <div className="flex gap-2">
          <PillButton label="Vendita" active={listingType === "sale"} onClick={() => setListingType(listingType === "sale" ? null : "sale")} />
          <PillButton label="Affitto" active={listingType === "rent"} onClick={() => setListingType(listingType === "rent" ? null : "rent")} />
        </div>
      </FilterSection>

      <FilterSection {...sectionProps} title="Pubblicato" count={publishedWithinDays || publishedAfter ? 1 : 0}>
        <div className="space-y-2">
          <select
            value={publishedWithinDays ?? ""}
            onChange={(e) => {
              setPublishedWithinDays(e.target.value ? parseInt(e.target.value) : null);
              setPublishedAfter(null);
            }}
            className={inputClass}
            aria-label="Pubblicato nel periodo"
          >
            <option value="">Qualsiasi data</option>
            {PUBLISHED_OPTIONS.map(({ days, label }) => (
              <option key={days} value={days}>{label}</option>
            ))}
          </select>
          <label className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
            Dal
            <input
              type="date"
              value={publishedAfter ?? ""}
              max={today}
              onChange={(e) => {
                setPublishedAfter(e.target.value || null);
                setPublishedWithinDays(null);
              }}
              className={inputClass}
            />
          </label>
        </div>
      </FilterSection>

      <FilterSection {...sectionProps} title="Aste" count={isAuction !== null ? 1 : 0}>
        <div className="flex flex-wrap gap-2">
          <PillButton label="Tutte" active={isAuction === null} onClick={() => setIsAuction(null)} />
          <PillButton label="Solo aste" active={isAuction === true} onClick={() => setIsAuction(isAuction === true ? null : true)} />
          <PillButton label="Escludi aste" active={isAuction === false} onClick={() => setIsAuction(isAuction === false ? null : false)} />
        </div>
      </FilterSection>

      <FilterSection {...sectionProps} title="Dove" count={(city ? 1 : 0) + (zone ? 1 : 0)}>
        <div className="space-y-2">
          <input type="text" value={city || ""} onChange={(e) => setCity(e.target.value || null)} placeholder="Citta (es. Roma)" className={inputClass} />
          <input type="text" value={zone || ""} onChange={(e) => setZone(e.target.value || null)} placeholder="Zona (es. Centro)" className={inputClass} />
        </div>
      </FilterSection>

      <FilterSection {...sectionProps} title="Tipologia" count={propertyType ? 1 : 0}>
        <div className="flex flex-wrap gap-2">
          {[
            { value: "apartment", label: "Appartamento" },
            { value: "house", label: "Casa" },
            { value: "villa", label: "Villa" },
            { value: "loft", label: "Loft" },
            { value: "studio", label: "Monolocale" },
          ].map(({ value, label }) => (
            <PillButton key={value} label={label} active={propertyType === value} onClick={() => setPropertyType(propertyType === value ? null : value)} />
          ))}
        </div>
      </FilterSection>

      <FilterSection {...sectionProps} title="Prezzo" count={(priceMin ? 1 : 0) + (priceMax ? 1 : 0)}>
        <div className="flex gap-2 items-center">
          <div className="relative flex-1">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-[var(--muted-foreground)]">EUR</span>
            <input type="number" value={priceMin || ""} onChange={(e) => setPriceMin(e.target.value ? parseInt(e.target.value) : null)} placeholder="Min" className={cn(inputClass, "pl-11")} />
          </div>
          <span className="text-[var(--muted-foreground)] text-sm">-</span>
          <div className="relative flex-1">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-[var(--muted-foreground)]">EUR</span>
            <input type="number" value={priceMax || ""} onChange={(e) => setPriceMax(e.target.value ? parseInt(e.target.value) : null)} placeholder="Max" className={cn(inputClass, "pl-11")} />
          </div>
        </div>
      </FilterSection>

      <FilterSection {...sectionProps} title="Superficie" count={(areaMin ? 1 : 0) + (areaMax ? 1 : 0)}>
        <div className="flex gap-2 items-center">
          <div className="relative flex-1">
            <input type="number" value={areaMin || ""} onChange={(e) => setAreaMin(e.target.value ? parseInt(e.target.value) : null)} placeholder="Min" className={inputClass} />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-[var(--muted-foreground)]">m&sup2;</span>
          </div>
          <span className="text-[var(--muted-foreground)] text-sm">-</span>
          <div className="relative flex-1">
            <input type="number" value={areaMax || ""} onChange={(e) => setAreaMax(e.target.value ? parseInt(e.target.value) : null)} placeholder="Max" className={inputClass} />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-[var(--muted-foreground)]">m&sup2;</span>
          </div>
        </div>
      </FilterSection>

      <FilterSection {...sectionProps} title="Locali" count={roomsMin ? 1 : 0}>
        <div className="flex gap-1.5">
          {[1, 2, 3, 4, 5].map((n) => (
            <NumberButton key={n} value={n} label={n === 5 ? "5+" : `${n}`} current={roomsMin} onClick={setRoomsMin} />
          ))}
        </div>
      </FilterSection>

      <FilterSection {...sectionProps} title="Bagni" defaultOpen={false} count={bathroomsMin ? 1 : 0}>
        <div className="flex gap-1.5">
          {[1, 2, 3].map((n) => (
            <NumberButton key={n} value={n} label={n === 3 ? "3+" : `${n}`} current={bathroomsMin} onClick={setBathroomsMin} />
          ))}
        </div>
      </FilterSection>

      <FilterSection {...sectionProps} title="Piano" defaultOpen={false} count={(floorMin ? 1 : 0) + (floorMax ? 1 : 0)}>
        <div className="flex gap-2 items-center">
          <select value={floorMin ?? ""} onChange={(e) => setFloorMin(e.target.value ? parseInt(e.target.value) : null)} className={inputClass}>
            <option value="">Da</option>
            <option value="0">Terra</option>
            <option value="1">1&deg;</option>
            <option value="2">2&deg;</option>
            <option value="3">3&deg;</option>
            <option value="4">4&deg;</option>
            <option value="5">5&deg;</option>
            <option value="6">6&deg;+</option>
          </select>
          <span className="text-[var(--muted-foreground)] text-sm">-</span>
          <select value={floorMax ?? ""} onChange={(e) => setFloorMax(e.target.value ? parseInt(e.target.value) : null)} className={inputClass}>
            <option value="">A</option>
            <option value="0">Terra</option>
            <option value="1">1&deg;</option>
            <option value="2">2&deg;</option>
            <option value="3">3&deg;</option>
            <option value="4">4&deg;</option>
            <option value="5">5&deg;</option>
            <option value="10">Alto</option>
          </select>
        </div>
      </FilterSection>

      <FilterSection {...sectionProps}
        title="Caratteristiche"
        defaultOpen={false}
        count={[hasElevator, hasBalcony, hasTerrace, hasGarage, hasGarden].filter(Boolean).length}
      >
        <div className="space-y-2.5">
          <Checkbox label="Ascensore" checked={hasElevator === true} onChange={(v) => setHasElevator(v ? true : null)} />
          <Checkbox label="Balcone" checked={hasBalcony === true} onChange={(v) => setHasBalcony(v ? true : null)} />
          <Checkbox label="Terrazzo" checked={hasTerrace === true} onChange={(v) => setHasTerrace(v ? true : null)} />
          <Checkbox label="Garage / Box" checked={hasGarage === true} onChange={(v) => setHasGarage(v ? true : null)} />
          <Checkbox label="Giardino" checked={hasGarden === true} onChange={(v) => setHasGarden(v ? true : null)} />
        </div>
      </FilterSection>

      <FilterSection {...sectionProps} title="Classe energetica" defaultOpen={false} count={energyClass ? 1 : 0}>
        <select value={energyClass || ""} onChange={(e) => setEnergyClass(e.target.value || null)} className={inputClass}>
          <option value="">Qualsiasi</option>
          {["A4", "A3", "A2", "A1", "B", "C", "D", "E", "F", "G"].map((c) => (
            <option key={c} value={c}>Classe {c}</option>
          ))}
        </select>
      </FilterSection>

      <FilterSection {...sectionProps} title="Stato immobile" defaultOpen={false} count={condition ? 1 : 0}>
        <select value={condition || ""} onChange={(e) => setCondition(e.target.value || null)} className={inputClass}>
          <option value="">Qualsiasi</option>
          <option value="nuovo">Nuovo</option>
          <option value="ristrutturato">Ristrutturato</option>
          <option value="buono">Buono stato</option>
          <option value="da_ristrutturare">Da ristrutturare</option>
        </select>
      </FilterSection>

      <FilterSection {...sectionProps} title="Fonte" defaultOpen={false} count={sourcePortal ? 1 : 0}>
        <div className="flex flex-wrap gap-2">
          {[
            { value: "immobiliare", label: "Immobiliare.it" },
            { value: "casa", label: "Casa.it" },
            { value: "tecnocasa", label: "Tecnocasa" },
            { value: "remax", label: "RE/MAX" },
            { value: "gabetti", label: "Gabetti" },
            { value: "vistocasa", label: "Vistocasa" },
          ].map(({ value, label }) => (
            <PillButton key={value} label={label} active={sourcePortal === value} onClick={() => setSourcePortal(sourcePortal === value ? null : value)} />
          ))}
        </div>
      </FilterSection>
      </div>
    </div>
  );
}
