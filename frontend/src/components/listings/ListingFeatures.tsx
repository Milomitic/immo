import type { LucideIcon } from "lucide-react";
import type { Listing } from "@/lib/types";
import { cn, floorLabel, formatArea } from "@/lib/utils";
import { FACT_ICONS, presentAmenities, type AmenityKey } from "./featureIcons";

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

interface Fact {
  key: string;
  icon: LucideIcon;
  /** Shown next to the icon. */
  text: string;
  /** Read by screen readers and shown on hover: the bare "3" needs context. */
  label: string;
}

/**
 * Rooms · area · bathrooms · floor, each with its icon, separated by thin
 * rules. ``verbose`` spells the units out ("3 locali") where there's room;
 * otherwise only the numbers show and the meaning is in the tooltip.
 */
export function KeyFacts({
  listing,
  verbose = false,
}: {
  listing: Pick<Listing, "rooms" | "area_sqm"> & Partial<Pick<Listing, "bathrooms" | "floor">>;
  verbose?: boolean;
}) {
  const facts: Fact[] = [];
  if (listing.rooms) {
    const label = plural(listing.rooms, "locale", "locali");
    facts.push({ key: "rooms", icon: FACT_ICONS.rooms, text: verbose ? label : `${listing.rooms}`, label });
  }
  if (listing.area_sqm) {
    const area = formatArea(listing.area_sqm);
    facts.push({ key: "area", icon: FACT_ICONS.area, text: area, label: `Superficie ${area}` });
  }
  if (listing.bathrooms) {
    const label = plural(listing.bathrooms, "bagno", "bagni");
    facts.push({ key: "bathrooms", icon: FACT_ICONS.bathrooms, text: verbose ? label : `${listing.bathrooms}`, label });
  }
  if (listing.floor) {
    const floor = floorLabel(listing.floor);
    facts.push({ key: "floor", icon: FACT_ICONS.floor, text: floor, label: floor });
  }

  return (
    <>
      {facts.map(({ key, icon: Icon, text, label }, i) => (
        <span
          key={key}
          title={label}
          className={cn(
            "flex items-center gap-1 whitespace-nowrap",
            i > 0 && "pl-2.5",
            i < facts.length - 1 && "pr-2.5 border-r border-[var(--border)]",
          )}
        >
          <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden />
          <span aria-hidden={text !== label}>{text}</span>
          {text !== label && <span className="sr-only">{label}</span>}
        </span>
      ))}
    </>
  );
}

/** The listing's amenities (lift, balcony, …) as small icons with tooltips. */
export function AmenityIcons({
  listing,
  className,
}: {
  listing: Pick<Listing, AmenityKey>;
  className?: string;
}) {
  const present = presentAmenities(listing);
  if (present.length === 0) return null;
  return (
    <ul className={cn("flex items-center gap-1.5", className)} aria-label="Dotazioni">
      {present.map(({ key, label, icon: Icon }) => (
        <li key={key} title={label} className="text-[var(--muted-foreground)]">
          <Icon className="h-3.5 w-3.5" aria-hidden />
          <span className="sr-only">{label}</span>
        </li>
      ))}
    </ul>
  );
}
