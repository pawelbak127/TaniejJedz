export const APP_NAME = 'TaniejJedz.pl';
export const APP_DESCRIPTION = 'Porównaj ceny dostaw jedzenia w Twojej okolicy. Sprawdzamy Pyszne.pl, Uber Eats, Wolt i Glovo — żebyś płacił mniej.';
export const APP_URL = process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000';

export const SUPPORTED_CITIES = ['warszawa'] as const;
export const SUPPORTED_CITIES_DISPLAY: Record<string, string> = {
  warszawa: 'Warszawa',
};
export const UPCOMING_CITIES = ['Kraków', 'Wrocław'];

export const API_BASE = '/api/v1';

export const SEARCH_DEFAULTS = {
  radius_km: 3,
  per_page: 20,
  show_closed: false,
  sort_by: 'relevance' as const,
};

export const SSE_TIMEOUT_MS = 15000;
export const SSE_MAX_RETRIES = 3;

export const DEBOUNCE_ADDRESS_MS = 300;
export const MAX_ADDRESS_SUGGESTIONS = 5;

export const TOAST_DURATION_MS = 4000;
export const MAX_TOASTS = 3;

export const STALENESS_THRESHOLDS = {
  fresh: 5 * 60,
  mild: 30 * 60,
} as const;

export const MIN_TOUCH_TARGET = 44;
