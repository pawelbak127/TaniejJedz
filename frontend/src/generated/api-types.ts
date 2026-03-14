// Auto-generated from OpenAPI spec — do not edit manually
// Phase 2: regenerate with `npm run generate-types`

export type Platform = "pyszne" | "ubereats" | "wolt" | "glovo";

export interface Address {
  formatted: string;
  latitude: number;
  longitude: number;
  city: string;
}

export interface SearchRequest {
  address: string;
  latitude: number;
  longitude: number;
  radius_km?: number;
  cuisine_filter?: string[];
  sort_by?: "relevance" | "cheapest_delivery" | "rating";
  show_closed?: boolean;
  page?: number;
  per_page?: number;
}

export interface SearchResponse {
  restaurants: RestaurantSummary[];
  total: number;
  page: number;
  per_page: number;
  city: string;
  data_freshness: Record<Platform, {
    checked_at: string;
    is_live: boolean;
  }>;
}

export interface RestaurantSummary {
  id: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  cuisine_tags: string[];
  image_url: string | null;
  data_quality_score: number;
  platforms: Partial<Record<Platform, PlatformAvailability>>;
  cheapest_open_platform: Platform | null;
  cheapest_delivery_fee_grosz: number | null;
}

export interface PlatformAvailability {
  available: boolean;
  is_open: boolean;
  next_open?: string;
  rating?: number;
  delivery_minutes?: number | null;
  delivery_fee_grosz?: number | null;
}

export interface MenuResponse {
  restaurant: {
    id: string;
    name: string;
    platforms_available: Platform[];
    platforms_open: Platform[];
    platforms_closed: { platform: Platform; next_open: string }[];
  };
  categories: MenuCategory[];
  platform_exclusive_items: Partial<Record<Platform, ExclusiveItem[]>>;
}

export interface MenuCategory {
  name: string;
  items: MenuItem[];
}

export interface MenuItem {
  id: string;
  name: string;
  description: string;
  size_label: string | null;
  image_url: string | null;
  prices: Partial<Record<Platform, PlatformPrice>>;
  cheapest_open_platform: Platform | null;
  savings_grosz: number;
  platform_modifiers: Partial<Record<Platform, ModifierGroup[]>>;
}

export interface PlatformPrice {
  price_grosz: number;
  is_available: boolean;
  is_open: boolean;
  last_checked: string;
}

export interface ModifierGroup {
  id: string;
  name: string;
  type: "required" | "optional";
  min_selections: number;
  max_selections: number;
  options: ModifierOption[];
}

export interface ModifierOption {
  id: string;
  name: string;
  price_grosz: number;
  is_default: boolean;
  is_available: boolean;
}

export interface ExclusiveItem {
  name: string;
  price_grosz: number;
  description: string;
  platform: Platform;
}

export interface CompareRequest {
  restaurant_id: string;
  address: { latitude: number; longitude: number };
  items: CartItem[];
}

export interface CartItem {
  canonical_item_id: string;
  quantity: number;
  selected_modifiers: Partial<Record<Platform, string[]>>;
}

export interface CompareResponse {
  comparison_id: string;
  status: "processing" | "already_processing";
}

export interface SSEPlatformStatus {
  event: "platform_status";
  platform: Platform;
  status: "fetching" | "ready" | "cached" | "timeout" | "closed" | "error";
  age_seconds?: number;
  next_open?: string;
  data?: PlatformComparisonResult;
}

export interface SSEComparisonReady {
  event: "ready";
  cheapest_open: Platform | null;
  savings_grosz: number;
  savings_display: string;
}

export interface SSETimeout {
  event: "timeout";
}

export interface PlatformComparisonResult {
  platform: Platform;
  is_open: boolean;
  next_open?: string;
  items: ComparisonItem[];
  items_total_grosz: number;
  delivery_fee_grosz: number;
  promotion_discount_grosz: number;
  grand_total_grosz: number;
  meets_minimum_order: boolean;
  minimum_order_grosz?: number;
  estimated_delivery_minutes: number | null;
  missing_items: string[];
  deep_link: string;
}

export interface ComparisonItem {
  canonical_item_id: string;
  name: string;
  quantity: number;
  unit_price_grosz: number;
  modifiers_price_grosz: number;
  item_total_grosz: number;
}

export interface FeedbackRequest {
  feedback_type: "wrong_price" | "wrong_match" | "other";
  canonical_restaurant_id?: string;
  platform_menu_item_id?: string;
  description?: string;
  context_snapshot: Record<string, unknown>;
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    retry: boolean;
  };
}
