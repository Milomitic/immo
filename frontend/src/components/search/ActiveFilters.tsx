"use client";

import { useQueryState, parseAsInteger, parseAsString, parseAsBoolean } from "nuqs";
import { Badge } from "@/components/ui/Badge";
import { formatPriceCompact, portalLabel, propertyTypeLabel } from "@/lib/utils";

export function ActiveFilters() {
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
  const [floorMin, setFloorMin] = useQueryState("floor_min", parseAsInteger);
  const [floorMax, setFloorMax] = useQueryState("floor_max", parseAsInteger);
  const [energyClass, setEnergyClass] = useQueryState("energy_class", parseAsString);
  const [condition, setCondition] = useQueryState("condition", parseAsString);
  const [hasElevator, setHasElevator] = useQueryState("has_elevator", parseAsBoolean);
  const [hasBalcony, setHasBalcony] = useQueryState("has_balcony", parseAsBoolean);
  const [hasTerrace, setHasTerrace] = useQueryState("has_terrace", parseAsBoolean);
  const [hasGarage, setHasGarage] = useQueryState("has_garage", parseAsBoolean);
  const [hasGarden, setHasGarden] = useQueryState("has_garden", parseAsBoolean);
  const [sourcePortal, setSourcePortal] = useQueryState("source_portal", parseAsString);
  const [polygon, setPolygon] = useQueryState("polygon", parseAsString);
  const [q, setQ] = useQueryState("q", parseAsString);

  const filters: { label: string; clear: () => void }[] = [];

  if (q) filters.push({ label: `Testo: "${q}"`, clear: () => setQ(null) });

  // Polygon chip first — it's the most "physical" filter, easy to
  // forget you have it active when you switch views.
  if (polygon) {
    const vertexCount = polygon.split(";").filter(Boolean).length;
    filters.push({
      label: `Area disegnata (${vertexCount} pt)`,
      clear: () => setPolygon(null),
    });
  }

  if (listingType) filters.push({ label: listingType === "sale" ? "Vendita" : "Affitto", clear: () => setListingType(null) });
  if (city) filters.push({ label: city.charAt(0).toUpperCase() + city.slice(1), clear: () => setCity(null) });
  if (zone) filters.push({ label: `Zona: ${zone}`, clear: () => setZone(null) });
  if (propertyType) filters.push({ label: propertyTypeLabel(propertyType), clear: () => setPropertyType(null) });

  if (priceMin && priceMax) {
    filters.push({ label: `\u20AC ${formatPriceCompact(priceMin)} - ${formatPriceCompact(priceMax)}`, clear: () => { setPriceMin(null); setPriceMax(null); } });
  } else if (priceMin) {
    filters.push({ label: `da \u20AC ${formatPriceCompact(priceMin)}`, clear: () => setPriceMin(null) });
  } else if (priceMax) {
    filters.push({ label: `fino a \u20AC ${formatPriceCompact(priceMax)}`, clear: () => setPriceMax(null) });
  }

  if (areaMin && areaMax) {
    filters.push({ label: `${areaMin} - ${areaMax} m\u00B2`, clear: () => { setAreaMin(null); setAreaMax(null); } });
  } else if (areaMin) {
    filters.push({ label: `da ${areaMin} m\u00B2`, clear: () => setAreaMin(null) });
  } else if (areaMax) {
    filters.push({ label: `fino a ${areaMax} m\u00B2`, clear: () => setAreaMax(null) });
  }

  if (roomsMin) filters.push({ label: `${roomsMin}+ locali`, clear: () => setRoomsMin(null) });
  if (bathroomsMin) filters.push({ label: `${bathroomsMin}+ bagni`, clear: () => setBathroomsMin(null) });

  if (floorMin !== null && floorMax !== null) {
    filters.push({ label: `Piano ${floorMin}-${floorMax}`, clear: () => { setFloorMin(null); setFloorMax(null); } });
  } else if (floorMin !== null) {
    filters.push({ label: `Piano ${floorMin}+`, clear: () => setFloorMin(null) });
  } else if (floorMax !== null) {
    filters.push({ label: `Piano fino a ${floorMax}`, clear: () => setFloorMax(null) });
  }
  if (energyClass) filters.push({ label: `Classe ${energyClass}`, clear: () => setEnergyClass(null) });
  if (condition) filters.push({ label: condition, clear: () => setCondition(null) });
  if (hasElevator) filters.push({ label: "Ascensore", clear: () => setHasElevator(null) });
  if (hasBalcony) filters.push({ label: "Balcone", clear: () => setHasBalcony(null) });
  if (hasTerrace) filters.push({ label: "Terrazzo", clear: () => setHasTerrace(null) });
  if (hasGarage) filters.push({ label: "Garage", clear: () => setHasGarage(null) });
  if (hasGarden) filters.push({ label: "Giardino", clear: () => setHasGarden(null) });
  if (sourcePortal) filters.push({ label: `Fonte: ${portalLabel(sourcePortal)}`, clear: () => setSourcePortal(null) });

  if (filters.length === 0) return null;

  const clearAll = () => filters.forEach(f => f.clear());

  return (
    <div className="flex flex-wrap items-center gap-2">
      {filters.map((f, i) => (
        <Badge key={i} variant="outline" size="md" removable onRemove={f.clear}>
          {f.label}
        </Badge>
      ))}
      {filters.length > 1 && (
        <button onClick={clearAll} className="text-xs font-medium text-[var(--primary)] hover:underline ml-1">
          Rimuovi tutti
        </button>
      )}
    </div>
  );
}
