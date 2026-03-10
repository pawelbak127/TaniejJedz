export const APP_NAME = "TaniejJedz.pl";
export const SUPPORTED_CITIES = ["Warszawa"];

export const DEFAULT_SEARCH_RADIUS_KM = 3;
export const ITEMS_PER_PAGE = 20;

export const API_BASE = "/api/v1";

export const ERROR_MESSAGES = {
  GENERIC: "Wystąpił nieoczekiwany błąd. Spróbuj ponownie.",
  NETWORK: "Błąd połączenia. Sprawdź swoje połączenie z internetem.",
  UNSUPPORTED_CITY: "Obsługujemy obecnie: Warszawa",
  EMPTY_CART_COMPARE: "Dodaj produkty do koszyka przed porównaniem.",
} as const;