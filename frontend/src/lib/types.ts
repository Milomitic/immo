export interface Listing {
  id: string;
  title: string;
  description: string | null;
  price: number | null;
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

export interface ListingDetail extends Listing {
  sources: ListingSource[];
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
  sort?: string;
  page?: number;
  page_size?: number;
}

export interface ListingMarker {
  id: string;
  lat: number;
  lng: number;
  price: number | null;
  title: string;
  property_type: string;
  listing_type: string;
  city: string;
  zone: string | null;
  area_sqm: number | null;
  rooms: number | null;
  thumbnail: string | null;
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
}
