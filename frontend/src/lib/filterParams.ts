/**
 * URL query keys that define *which* listings a search returns. They are
 * named exactly like the API parameters, so a search is just this subset
 * of the URL: carried across /search ↔ /map, and stored by saved searches.
 *
 * ``bbox`` is deliberately absent: it's the map viewport and would clip the
 * list. ``polygon`` is present: it's a perimeter the user drew on purpose.
 */
export const FILTER_PARAM_KEYS = [
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
] as const;

/** "What changed since" filters. A saved search applies its own. */
export const SINCE_PARAM_KEYS = ["first_seen_after", "price_drop_since"] as const;

/** How results are shown rather than which ones. */
export const VIEW_PARAM_KEYS = ["sort", "page_size"] as const;

export function pickParams(source: URLSearchParams, keys: readonly string[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const key of keys) {
    const value = source.get(key);
    if (value) out[key] = value;
  }
  return out;
}

export function toQueryString(params: Record<string, string>): string {
  const qs = new URLSearchParams(params).toString();
  return qs ? `?${qs}` : "";
}
