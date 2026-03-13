export type Platform = "pyszne" | "ubereats" | "wolt" | "glovo";

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

interface PlatformAvailability {
  available: boolean;
  is_open: boolean;
  next_open?: string;
  rating?: number;
  delivery_minutes?: number | null;
  delivery_fee_grosz?: number | null;
}

export const RESTAURANTS: RestaurantSummary[] = [
  {
    id: "rest-001",
    name: "Pizzeria Roma",
    address: "ul. Nowy Świat 42, Warszawa",
    latitude: 52.2310,
    longitude: 21.0180,
    cuisine_tags: ["pizza", "włoska"],
    image_url: null,
    data_quality_score: 0.92,
    platforms: {
      pyszne: { available: true, is_open: true, rating: 4.5, delivery_minutes: 35, delivery_fee_grosz: 599 },
      wolt: { available: true, is_open: true, rating: 4.6, delivery_minutes: 30, delivery_fee_grosz: 399 },
      ubereats: { available: true, is_open: true, rating: 4.3, delivery_minutes: 40, delivery_fee_grosz: 999 },
      glovo: { available: false, is_open: false },
    },
    cheapest_open_platform: "wolt",
    cheapest_delivery_fee_grosz: 399,
  },
  {
    id: "rest-002",
    name: "Sushi Master",
    address: "ul. Chmielna 8, Warszawa",
    latitude: 52.2325,
    longitude: 21.0090,
    cuisine_tags: ["sushi", "japońska"],
    image_url: null,
    data_quality_score: 0.88,
    platforms: {
      pyszne: { available: true, is_open: true, rating: 4.7, delivery_minutes: 45, delivery_fee_grosz: 799 },
      wolt: { available: true, is_open: false, next_open: "18:00", rating: 4.8, delivery_minutes: null, delivery_fee_grosz: null },
      ubereats: { available: true, is_open: true, rating: 4.5, delivery_minutes: 50, delivery_fee_grosz: 999 },
    },
    cheapest_open_platform: "pyszne",
    cheapest_delivery_fee_grosz: 799,
  },
  {
    id: "rest-003",
    name: "Kebab u Alego",
    address: "ul. Marszałkowska 73, Warszawa",
    latitude: 52.2270,
    longitude: 21.0150,
    cuisine_tags: ["kebab", "turecka"],
    image_url: null,
    data_quality_score: 0.85,
    platforms: {
      pyszne: { available: true, is_open: true, rating: 4.2, delivery_minutes: 25, delivery_fee_grosz: 499 },
      wolt: { available: true, is_open: true, rating: 4.0, delivery_minutes: 20, delivery_fee_grosz: 299 },
      glovo: { available: true, is_open: true, rating: 3.9, delivery_minutes: 30, delivery_fee_grosz: 599 },
    },
    cheapest_open_platform: "wolt",
    cheapest_delivery_fee_grosz: 299,
  },
  {
    id: "rest-004",
    name: "Burger Craft",
    address: "ul. Mokotowska 17, Warszawa",
    latitude: 52.2205,
    longitude: 21.0160,
    cuisine_tags: ["burgery", "amerykańska"],
    image_url: null,
    data_quality_score: 0.90,
    platforms: {
      pyszne: { available: true, is_open: true, rating: 4.4, delivery_minutes: 30, delivery_fee_grosz: 699 },
      wolt: { available: true, is_open: true, rating: 4.5, delivery_minutes: 25, delivery_fee_grosz: 499 },
      ubereats: { available: true, is_open: true, rating: 4.6, delivery_minutes: 35, delivery_fee_grosz: 799 },
      glovo: { available: true, is_open: true, rating: 4.2, delivery_minutes: 40, delivery_fee_grosz: 699 },
    },
    cheapest_open_platform: "wolt",
    cheapest_delivery_fee_grosz: 499,
  },
  {
    id: "rest-005",
    name: "Pad Thai Express",
    address: "ul. Koszykowa 55, Warszawa",
    latitude: 52.2220,
    longitude: 21.0100,
    cuisine_tags: ["tajska", "azjatycka"],
    image_url: null,
    data_quality_score: 0.78,
    platforms: {
      pyszne: { available: true, is_open: true, rating: 4.1, delivery_minutes: 40, delivery_fee_grosz: 599 },
      wolt: { available: true, is_open: true, rating: 4.3, delivery_minutes: 35, delivery_fee_grosz: 499 },
    },
    cheapest_open_platform: "wolt",
    cheapest_delivery_fee_grosz: 499,
  },
  {
    id: "rest-006",
    name: "Smaki Gruzji",
    address: "ul. Wilcza 29, Warszawa",
    latitude: 52.2240,
    longitude: 21.0130,
    cuisine_tags: ["gruzińska", "chaczapuri"],
    image_url: null,
    data_quality_score: 0.95,
    platforms: {
      pyszne: { available: true, is_open: false, next_open: "11:00", rating: 4.8 },
      wolt: { available: true, is_open: false, next_open: "11:00", rating: 4.9 },
      ubereats: { available: true, is_open: false, next_open: "11:30", rating: 4.7 },
    },
    cheapest_open_platform: null,
    cheapest_delivery_fee_grosz: null,
  },
  {
    id: "rest-007",
    name: "Ramen Ichiban",
    address: "ul. Poznańska 12, Warszawa",
    latitude: 52.2250,
    longitude: 21.0140,
    cuisine_tags: ["ramen", "japońska"],
    image_url: null,
    data_quality_score: 0.91,
    platforms: {
      wolt: { available: true, is_open: true, rating: 4.7, delivery_minutes: 35, delivery_fee_grosz: 599 },
      ubereats: { available: true, is_open: true, rating: 4.5, delivery_minutes: 45, delivery_fee_grosz: 899 },
    },
    cheapest_open_platform: "wolt",
    cheapest_delivery_fee_grosz: 599,
  },
  {
    id: "rest-008",
    name: "Zapiecek — Pierogi",
    address: "ul. Nowy Świat 64, Warszawa",
    latitude: 52.2300,
    longitude: 21.0175,
    cuisine_tags: ["polska", "pierogi"],
    image_url: null,
    data_quality_score: 0.87,
    platforms: {
      pyszne: { available: true, is_open: true, rating: 4.3, delivery_minutes: 30, delivery_fee_grosz: 499 },
      wolt: { available: true, is_open: true, rating: 4.4, delivery_minutes: 25, delivery_fee_grosz: 399 },
      ubereats: { available: true, is_open: true, rating: 4.1, delivery_minutes: 40, delivery_fee_grosz: 799 },
      glovo: { available: true, is_open: true, rating: 4.0, delivery_minutes: 35, delivery_fee_grosz: 599 },
    },
    cheapest_open_platform: "wolt",
    cheapest_delivery_fee_grosz: 399,
  },
  {
    id: "rest-009",
    name: "MEAT Burger Bar",
    address: "ul. Hożna 62, Warszawa",
    latitude: 52.2230,
    longitude: 21.0155,
    cuisine_tags: ["burgery", "amerykańska"],
    image_url: null,
    data_quality_score: 0.82,
    platforms: {
      ubereats: { available: true, is_open: true, rating: 4.6, delivery_minutes: 30, delivery_fee_grosz: 799 },
    },
    cheapest_open_platform: "ubereats",
    cheapest_delivery_fee_grosz: 799,
  },
  {
    id: "rest-010",
    name: "Olimp Greek Food",
    address: "ul. Bracka 20, Warszawa",
    latitude: 52.2290,
    longitude: 21.0165,
    cuisine_tags: ["grecka", "gyros"],
    image_url: null,
    data_quality_score: 0.89,
    platforms: {
      pyszne: { available: true, is_open: true, rating: 4.4, delivery_minutes: 35, delivery_fee_grosz: 599 },
      wolt: { available: true, is_open: true, rating: 4.5, delivery_minutes: 30, delivery_fee_grosz: 499 },
      glovo: { available: true, is_open: true, rating: 4.2, delivery_minutes: 40, delivery_fee_grosz: 699 },
    },
    cheapest_open_platform: "wolt",
    cheapest_delivery_fee_grosz: 499,
  },
  {
    id: "rest-011",
    name: "Kuchnia Marché",
    address: "ul. Świętokrzyska 18, Warszawa",
    latitude: 52.2350,
    longitude: 21.0120,
    cuisine_tags: ["polska", "obiad"],
    image_url: null,
    data_quality_score: 0.75,
    platforms: {
      pyszne: { available: true, is_open: true, rating: 4.0, delivery_minutes: 40, delivery_fee_grosz: 699 },
    },
    cheapest_open_platform: "pyszne",
    cheapest_delivery_fee_grosz: 699,
  },
  {
    id: "rest-012",
    name: "Ciao Napoli",
    address: "ul. Foksal 3, Warszawa",
    latitude: 52.2315,
    longitude: 21.0195,
    cuisine_tags: ["pizza", "włoska", "makarony"],
    image_url: null,
    data_quality_score: 0.93,
    platforms: {
      pyszne: { available: true, is_open: true, rating: 4.6, delivery_minutes: 35, delivery_fee_grosz: 599 },
      wolt: { available: true, is_open: true, rating: 4.7, delivery_minutes: 30, delivery_fee_grosz: 499 },
      ubereats: { available: true, is_open: true, rating: 4.5, delivery_minutes: 40, delivery_fee_grosz: 899 },
    },
    cheapest_open_platform: "wolt",
    cheapest_delivery_fee_grosz: 499,
  },
];

// ============================================================
// MENU — Full menu for rest-001 (Pizzeria Roma)
// ============================================================

export const MENU_REST_001 = {
  restaurant: {
    id: "rest-001",
    name: "Pizzeria Roma",
    platforms_available: ["pyszne", "wolt", "ubereats"] as Platform[],
    platforms_open: ["pyszne", "wolt", "ubereats"] as Platform[],
    platforms_closed: [] as { platform: Platform; next_open: string }[],
  },
  categories: [
    {
      name: "Pizza",
      items: [
        {
          id: "item-001",
          name: "Margherita",
          description: "Sos pomidorowy, mozzarella, świeża bazylia",
          size_label: "32cm",
          image_url: null,
          prices: {
            pyszne: { price_grosz: 2800, is_available: true, is_open: true, last_checked: new Date().toISOString() },
            wolt: { price_grosz: 2650, is_available: true, is_open: true, last_checked: new Date().toISOString() },
            ubereats: { price_grosz: 3200, is_available: true, is_open: true, last_checked: new Date().toISOString() },
          },
          cheapest_open_platform: "wolt" as Platform,
          savings_grosz: 550,
          platform_modifiers: {
            pyszne: [
              {
                id: "mod-p-size", name: "Rozmiar", type: "required" as const, min_selections: 1, max_selections: 1,
                options: [
                  { id: "mod-p-30", name: "30cm", price_grosz: 0, is_default: true, is_available: true },
                  { id: "mod-p-40", name: "40cm", price_grosz: 800, is_default: false, is_available: true },
                  { id: "mod-p-50", name: "50cm (rodzinna)", price_grosz: 1600, is_default: false, is_available: true },
                ],
              },
              {
                id: "mod-p-extra", name: "Dodatki", type: "optional" as const, min_selections: 0, max_selections: 5,
                options: [
                  { id: "mod-p-cheese", name: "Dodatkowy ser", price_grosz: 500, is_default: false, is_available: true },
                  { id: "mod-p-ham", name: "Szynka", price_grosz: 600, is_default: false, is_available: true },
                  { id: "mod-p-mushroom", name: "Pieczarki", price_grosz: 400, is_default: false, is_available: true },
                  { id: "mod-p-olive", name: "Oliwki", price_grosz: 400, is_default: false, is_available: true },
                  { id: "mod-p-jalapeno", name: "Jalapeño", price_grosz: 300, is_default: false, is_available: true },
                ],
              },
            ],
            wolt: [
              {
                id: "mod-w-size", name: "Wielkość", type: "required" as const, min_selections: 1, max_selections: 1,
                options: [
                  { id: "mod-w-small", name: "Mała (30cm)", price_grosz: 0, is_default: true, is_available: true },
                  { id: "mod-w-large", name: "Duża (40cm)", price_grosz: 1000, is_default: false, is_available: true },
                  { id: "mod-w-family", name: "Rodzinna (50cm)", price_grosz: 1800, is_default: false, is_available: true },
                ],
              },
              {
                id: "mod-w-extra", name: "Extra toppings", type: "optional" as const, min_selections: 0, max_selections: 3,
                options: [
                  { id: "mod-w-cheese", name: "Cheese", price_grosz: 450, is_default: false, is_available: true },
                  { id: "mod-w-ham", name: "Ham", price_grosz: 500, is_default: false, is_available: true },
                  { id: "mod-w-mushroom", name: "Mushrooms", price_grosz: 400, is_default: false, is_available: true },
                ],
              },
            ],
            ubereats: [
              {
                id: "mod-u-size", name: "Choose size", type: "required" as const, min_selections: 1, max_selections: 1,
                options: [
                  { id: "mod-u-reg", name: "Regular (32cm)", price_grosz: 0, is_default: true, is_available: true },
                  { id: "mod-u-lg", name: "Large (40cm)", price_grosz: 1200, is_default: false, is_available: true },
                ],
              },
              {
                id: "mod-u-extra", name: "Add extras", type: "optional" as const, min_selections: 0, max_selections: 4,
                options: [
                  { id: "mod-u-cheese", name: "Extra Cheese", price_grosz: 600, is_default: false, is_available: true },
                  { id: "mod-u-pepperoni", name: "Pepperoni", price_grosz: 700, is_default: false, is_available: true },
                  { id: "mod-u-mushroom", name: "Mushrooms", price_grosz: 500, is_default: false, is_available: true },
                ],
              },
            ],
          },
        },
        {
          id: "item-002",
          name: "Pepperoni",
          description: "Sos pomidorowy, mozzarella, pepperoni, oregano",
          size_label: "32cm",
          image_url: null,
          prices: {
            pyszne: { price_grosz: 3200, is_available: true, is_open: true, last_checked: new Date().toISOString() },
            wolt: { price_grosz: 3000, is_available: true, is_open: true, last_checked: new Date().toISOString() },
            ubereats: { price_grosz: 3600, is_available: true, is_open: true, last_checked: new Date().toISOString() },
          },
          cheapest_open_platform: "wolt" as Platform,
          savings_grosz: 600,
          platform_modifiers: {
            pyszne: [
              {
                id: "mod-p2-size", name: "Rozmiar", type: "required" as const, min_selections: 1, max_selections: 1,
                options: [
                  { id: "mod-p2-30", name: "30cm", price_grosz: 0, is_default: true, is_available: true },
                  { id: "mod-p2-40", name: "40cm", price_grosz: 800, is_default: false, is_available: true },
                ],
              },
            ],
            wolt: [
              {
                id: "mod-w2-size", name: "Wielkość", type: "required" as const, min_selections: 1, max_selections: 1,
                options: [
                  { id: "mod-w2-small", name: "Mała (30cm)", price_grosz: 0, is_default: true, is_available: true },
                  { id: "mod-w2-large", name: "Duża (40cm)", price_grosz: 1000, is_default: false, is_available: true },
                ],
              },
            ],
            ubereats: [
              {
                id: "mod-u2-size", name: "Size", type: "required" as const, min_selections: 1, max_selections: 1,
                options: [
                  { id: "mod-u2-reg", name: "Regular", price_grosz: 0, is_default: true, is_available: true },
                  { id: "mod-u2-lg", name: "Large", price_grosz: 1200, is_default: false, is_available: true },
                ],
              },
            ],
          },
        },
        {
          id: "item-003",
          name: "Capricciosa",
          description: "Sos pomidorowy, mozzarella, szynka, pieczarki, oliwki",
          size_label: "32cm",
          image_url: null,
          prices: {
            pyszne: { price_grosz: 3400, is_available: true, is_open: true, last_checked: new Date().toISOString() },
            wolt: { price_grosz: 3100, is_available: true, is_open: true, last_checked: new Date().toISOString() },
            ubereats: { price_grosz: 3800, is_available: false, is_open: true, last_checked: new Date().toISOString() },
          },
          cheapest_open_platform: "wolt" as Platform,
          savings_grosz: 300,
          platform_modifiers: {},
        },
      ],
    },
    {
      name: "Makarony",
      items: [
        {
          id: "item-004",
          name: "Spaghetti Bolognese",
          description: "Makaron spaghetti, sos mięsny, parmezan",
          size_label: null,
          image_url: null,
          prices: {
            pyszne: { price_grosz: 2600, is_available: true, is_open: true, last_checked: new Date().toISOString() },
            wolt: { price_grosz: 2800, is_available: true, is_open: true, last_checked: new Date().toISOString() },
            ubereats: { price_grosz: 2900, is_available: true, is_open: true, last_checked: new Date().toISOString() },
          },
          cheapest_open_platform: "pyszne" as Platform,
          savings_grosz: 300,
          platform_modifiers: {},
        },
        {
          id: "item-005",
          name: "Penne Arrabiata",
          description: "Makaron penne, pikantny sos pomidorowy, czosnek",
          size_label: null,
          image_url: null,
          prices: {
            pyszne: { price_grosz: 2400, is_available: true, is_open: true, last_checked: new Date().toISOString() },
            wolt: { price_grosz: 2350, is_available: true, is_open: true, last_checked: new Date().toISOString() },
          },
          cheapest_open_platform: "wolt" as Platform,
          savings_grosz: 50,
          platform_modifiers: {},
        },
      ],
    },
    {
      name: "Desery",
      items: [
        {
          id: "item-006",
          name: "Tiramisu",
          description: "Klasyczne włoskie tiramisu z mascarpone",
          size_label: null,
          image_url: null,
          prices: {
            pyszne: { price_grosz: 1800, is_available: true, is_open: true, last_checked: new Date().toISOString() },
            wolt: { price_grosz: 1800, is_available: true, is_open: true, last_checked: new Date().toISOString() },
            ubereats: { price_grosz: 2200, is_available: true, is_open: true, last_checked: new Date().toISOString() },
          },
          cheapest_open_platform: "pyszne" as Platform,
          savings_grosz: 400,
          platform_modifiers: {},
        },
      ],
    },
  ],
  platform_exclusive_items: {
    ubereats: [
      { name: "Uber Combo: Pizza + Napój", price_grosz: 3500, description: "Dowolna pizza 30cm + Coca-Cola 0.5L", platform: "ubereats" as Platform },
    ],
  },
};

// ============================================================
// COMPARISON — SSE result simulation for rest-001
// ============================================================

export const COMPARISON_RESULT_REST_001 = {
  pyszne: {
    platform: "pyszne" as Platform,
    is_open: true,
    items: [
      { canonical_item_id: "item-001", name: "Margherita 40cm × 2", quantity: 2, unit_price_grosz: 3600, modifiers_price_grosz: 1000, item_total_grosz: 9200 },
      { canonical_item_id: "item-006", name: "Tiramisu × 1", quantity: 1, unit_price_grosz: 1800, modifiers_price_grosz: 0, item_total_grosz: 1800 },
    ],
    items_total_grosz: 11000,
    delivery_fee_grosz: 599,
    promotion_discount_grosz: 1000,
    grand_total_grosz: 10599,
    meets_minimum_order: true,
    minimum_order_grosz: 3000,
    estimated_delivery_minutes: 35,
    missing_items: [] as string[],
    deep_link: "/api/v1/redirect/pyszne/rest-001?session=mock-session",
  },
  wolt: {
    platform: "wolt" as Platform,
    is_open: true,
    items: [
      { canonical_item_id: "item-001", name: "Margherita Duża × 2", quantity: 2, unit_price_grosz: 3650, modifiers_price_grosz: 900, item_total_grosz: 9100 },
      { canonical_item_id: "item-006", name: "Tiramisu × 1", quantity: 1, unit_price_grosz: 1800, modifiers_price_grosz: 0, item_total_grosz: 1800 },
    ],
    items_total_grosz: 10900,
    delivery_fee_grosz: 399,
    promotion_discount_grosz: 0,
    grand_total_grosz: 11299,
    meets_minimum_order: true,
    minimum_order_grosz: 2500,
    estimated_delivery_minutes: 30,
    missing_items: [] as string[],
    deep_link: "/api/v1/redirect/wolt/rest-001?session=mock-session",
  },
  ubereats: {
    platform: "ubereats" as Platform,
    is_open: true,
    items: [
      { canonical_item_id: "item-001", name: "Margherita Large × 2", quantity: 2, unit_price_grosz: 4400, modifiers_price_grosz: 1200, item_total_grosz: 11200 },
      { canonical_item_id: "item-006", name: "Tiramisu × 1", quantity: 1, unit_price_grosz: 2200, modifiers_price_grosz: 0, item_total_grosz: 2200 },
    ],
    items_total_grosz: 13400,
    delivery_fee_grosz: 999,
    promotion_discount_grosz: 0,
    grand_total_grosz: 14399,
    meets_minimum_order: true,
    minimum_order_grosz: 4000,
    estimated_delivery_minutes: 40,
    missing_items: [] as string[],
    deep_link: "/api/v1/redirect/ubereats/rest-001?session=mock-session",
  },
};

// ============================================================
// HELPER: Generate menu for any restaurant
// ============================================================

export function getMenuForRestaurant(restaurantId: string) {
  if (restaurantId === "rest-001") return MENU_REST_001;

  const restaurant = RESTAURANTS.find(r => r.id === restaurantId);
  if (!restaurant) return null;

  const platforms = Object.entries(restaurant.platforms)
    .filter(([, v]) => v.available)
    .map(([k]) => k as Platform);

  const generatePrices = (base: number) => {
    const prices: Record<string, { price_grosz: number; is_available: boolean; is_open: boolean; last_checked: string }> = {};
    for (const p of platforms) {
      const variance = Math.round(base * (0.85 + Math.random() * 0.3));
      prices[p] = {
        price_grosz: variance,
        is_available: true,
        is_open: restaurant.platforms[p]?.is_open ?? false,
        last_checked: new Date().toISOString(),
      };
    }
    return prices;
  };

  const findCheapestOpen = (prices: Record<string, { price_grosz: number; is_open: boolean }>) => {
    let cheapest: Platform | null = null;
    let cheapestPrice = Infinity;
    for (const [p, v] of Object.entries(prices)) {
      if (v.is_open && v.price_grosz < cheapestPrice) {
        cheapestPrice = v.price_grosz;
        cheapest = p as Platform;
      }
    }
    return cheapest;
  };

  const item1Prices = generatePrices(2800);
  const item2Prices = generatePrices(3500);
  const item3Prices = generatePrices(1500);

  return {
    restaurant: {
      id: restaurantId,
      name: restaurant.name,
      platforms_available: platforms,
      platforms_open: platforms.filter(p => restaurant.platforms[p]?.is_open),
      platforms_closed: platforms
        .filter(p => !restaurant.platforms[p]?.is_open)
        .map(p => ({ platform: p, next_open: restaurant.platforms[p]?.next_open || "11:00" })),
    },
    categories: [
      {
        name: "Popularne",
        items: [
          {
            id: `${restaurantId}-item-1`,
            name: "Danie dnia",
            description: "Najpopularniejsze danie w restauracji",
            size_label: null,
            image_url: null,
            prices: item1Prices,
            cheapest_open_platform: findCheapestOpen(item1Prices),
            savings_grosz: 300,
            platform_modifiers: {},
          },
          {
            id: `${restaurantId}-item-2`,
            name: "Zestaw obiadowy",
            description: "Zupa + drugie danie",
            size_label: null,
            image_url: null,
            prices: item2Prices,
            cheapest_open_platform: findCheapestOpen(item2Prices),
            savings_grosz: 500,
            platform_modifiers: {},
          },
          {
            id: `${restaurantId}-item-3`,
            name: "Przystawka",
            description: "Przystawka dnia",
            size_label: null,
            image_url: null,
            prices: item3Prices,
            cheapest_open_platform: findCheapestOpen(item3Prices),
            savings_grosz: 200,
            platform_modifiers: {},
          },
        ],
      },
    ],
    platform_exclusive_items: {},
  };
}
