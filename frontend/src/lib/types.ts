/** How an estimated position was found: from the street and house
 *  number, or the middle of the street. Listings that name no street
 *  get no position at all. */
export type GeoPrecision = "address" | "street";

export interface Listing {
  id: string;
  title: string;
  description: string | null;
  price: number | null;
  price_previous: number | null;
  price_changed_at: string | null;
  price_per_sqm: number | null;
  area_sqm: number | null;
  rooms: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  floor: string | null;
  total_floors: number | null;
  address: string | null;
  city: string;
  zone: string | null;
  province: string | null;
  lat: number | null;
  lng: number | null;
  /** null: the portal's position; else how we estimated it. */
  geo_precision: GeoPrecision | null;
  images: string[];
  floor_plans: string[];
  listing_url: string;
  source_portal: string;
  source_id: string;
  energy_class: string | null;
  property_type: string;
  listing_type: string;
  condition: string | null;
  heating: string | null;
  has_elevator: boolean | null;
  has_balcony: boolean | null;
  has_terrace: boolean | null;
  has_garage: boolean | null;
  has_garden: boolean | null;
  condominium_fees: number | null;
  year_built: number | null;
  publication_date: string | null;
  /** Judicial / online auction rather than a normal sale. */
  is_auction: boolean;
  created_at: string;
  updated_at: string;
  first_seen_at: string;
  last_seen_at: string;
  is_active: boolean;
  source_count: number;
}

export interface ListingSource {
  id: string;
  source_portal: string;
  source_id: string;
  source_url: string;
  price_on_source: number | null;
  first_seen_at: string;
  last_seen_at: string;
  is_active: boolean;
}

/** A judicial auction's sale data. Times are local wall-clock values
 *  ("2027-01-22T16:30"). */
export interface AuctionInfo {
  date: string | null;
  base_price: number | null;
  minimum_offer: number | null;
  minimum_raise: number | null;
  offer_deadline: string | null;
  court: string | null;
  procedure: string | null;
  procedure_type: string | null;
  sale_mode: string | null;
  /** Visit booking on the Ministry's Portale Vendite Pubbliche. */
  pvp_url: string | null;
  documents: { name: string; url: string }[];
}

export interface ListingDetail extends Listing {
  sources: ListingSource[];
  auction: AuctionInfo | null;
}

/** A saved search: the /search filter params plus "what's new" counts. */
export interface SearchAlert {
  id: string;
  name: string;
  filters: Record<string, string>;
  /** E-mail digests on/off. */
  is_active: boolean;
  created_at: string;
  /** "New" is relative to this: the last time the user looked. */
  seen_at: string | null;
  last_notified_at: string | null;
  total: number;
  new_count: number;
  price_drop_count: number;
}

export interface Favorite {
  listing: Listing;
  created_at: string;
}

/** One observed price, oldest first in /price-history. */
export interface PricePoint {
  price: number;
  observed_at: string;
  source_portal: string | null;
}

export interface PaginatedListings {
  items: Listing[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ListingSearchParams {
  q?: string;
  city?: string;
  zone?: string;
  province?: string;
  listing_type?: string;
  property_type?: string;
  price_min?: number;
  price_max?: number;
  area_min?: number;
  area_max?: number;
  rooms_min?: number;
  rooms_max?: number;
  bedrooms_min?: number;
  bathrooms_min?: number;
  energy_class?: string;
  has_elevator?: boolean;
  has_balcony?: boolean;
  has_terrace?: boolean;
  has_garage?: boolean;
  has_garden?: boolean;
  floor_min?: number;
  floor_max?: number;
  condition?: string;
  source_portal?: string;
  price_per_sqm_min?: number;
  price_per_sqm_max?: number;
  year_built_min?: number;
  year_built_max?: number;
  bbox?: string;
  /** User-drawn polygon: ``"lat,lng;lat,lng;...;lat,lng"`` (>=3 vertices). */
  polygon?: string;
  /** ISO instant: only listings first seen after it. */
  first_seen_after?: string;
  /** ISO instant: only listings whose price dropped after it. */
  price_drop_since?: string;
  /** Published on the portal in the last N calendar days (1 = today). */
  published_within_days?: number;
  /** Published on the portal on/after this date (YYYY-MM-DD). */
  published_after?: string;
  /** true: auctions only; false: hide auctions. */
  is_auction?: boolean;
  sort?: string;
  page?: number;
  page_size?: number;
}

export interface ListingMarker {
  id: string;
  lat: number;
  lng: number;
  geo_precision: GeoPrecision | null;
  price: number | null;
  title: string;
  property_type: string;
  listing_type: string;
  city: string;
  zone: string | null;
  area_sqm: number | null;
  rooms: number | null;
  thumbnail: string | null;
  publication_date: string | null;
  is_auction: boolean;
  /** Portal of the canonical listing (where the data comes from). */
  source_portal: string;
}

export interface ListingMarkersResponse {
  markers: ListingMarker[];
  total: number;
  truncated: boolean;
}

export interface Stats {
  total_listings: number;
  active_listings: number;
  by_portal: Record<string, number>;
  by_city: Record<string, number>;
  avg_price_sqm_by_city: Record<string, number>;
  last_scrape_runs: ScrapeRun[];
}

export interface ScrapeRun {
  id: string;
  portal: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  listings_found: number;
  listings_new: number;
  listings_updated: number;
  listings_deactivated: number;
  errors: number;
  progress_done?: number | null;
  progress_total?: number | null;
  phase?: string | null;
  last_progress_at?: string | null;
  listings_seen?: number | null;
  coverage_complete?: boolean | null;
  job_id?: string | null;
}

export interface ScrapeStatus {
  is_running: boolean;
  is_stale: boolean;
  started_at: string | null;
  finished_at: string | null;
  seconds_since_last_progress: number | null;
  progress_done: number;
  progress_total: number;
  phase: string | null;
  runs: ScrapeRun[];
}

/** When the catalogue was last refreshed, overall and per portal. */
export interface LastUpdate {
  finished_at: string | null;
  /** Portals in the most recent job; fewer than all when it was partial. */
  portals: string[];
  is_full: boolean;
  by_portal: Record<string, string>;
}

export interface ScrapeTriggerResponse {
  accepted: boolean;
  portals: string[];
  city: string;
  started_at: string;
  message: string;
}
