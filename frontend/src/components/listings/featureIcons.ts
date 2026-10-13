import type { LucideIcon } from "lucide-react";
import {
  ArrowUpDown, Bath, BedDouble, Building, Building2, Car, DoorOpen, Euro, Fence,
  Flame, Hammer, Home, Maximize2, Receipt, Sparkles, Sun, Trees, Zap,
} from "lucide-react";
import type { Listing } from "@/lib/types";

/** One icon per characteristic, the same wherever a listing is shown. */
export const FACT_ICONS = {
  area: Maximize2,
  rooms: DoorOpen,
  bedrooms: BedDouble,
  bathrooms: Bath,
  floor: Building2,
  totalFloors: Building,
  pricePerSqm: Euro,
  propertyType: Home,
  condition: Sparkles,
  yearBuilt: Hammer,
  condominiumFees: Receipt,
  heating: Flame,
  energyClass: Zap,
} satisfies Record<string, LucideIcon>;

export type AmenityKey = "has_elevator" | "has_balcony" | "has_terrace" | "has_garage" | "has_garden";

export const AMENITIES: { key: AmenityKey; label: string; icon: LucideIcon }[] = [
  { key: "has_elevator", label: "Ascensore", icon: ArrowUpDown },
  { key: "has_balcony", label: "Balcone", icon: Fence },
  { key: "has_terrace", label: "Terrazzo", icon: Sun },
  { key: "has_garage", label: "Garage / box", icon: Car },
  { key: "has_garden", label: "Giardino", icon: Trees },
];

/** The amenities the listing is known to have (unknown ≠ absent: skipped). */
export function presentAmenities(listing: Pick<Listing, AmenityKey>) {
  return AMENITIES.filter((a) => listing[a.key] === true);
}
